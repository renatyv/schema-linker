from __future__ import annotations

from typing import Any

from datasketch import MinHash, MinHashLSHEnsemble
from sqlalchemy import Table, select
from sqlalchemy.engine import Connection

from schema_linker import query_timeout
from schema_linker.evidence import (
    get_cardinality_evidence,
    get_name_evidence,
    get_notes,
    is_primary_lsh_target,
    is_strong_name_candidate,
    normalize_value,
    plausible_direction,
    spot_check_overlap,
    stable_hash_value,
    stable_sort_value,
)
from schema_linker.models import (
    CandidatePair,
    ColumnRef,
    DeclaredLink,
    InferredLink,
    SchemaLinkOptions,
    SchemaLinkProgress,
)


def infer_links(
    conn: Connection,
    tables: list[Table],
    column_refs: dict[tuple[str, str], ColumnRef],
    declared_links: list[DeclaredLink],
    options: SchemaLinkOptions,
    progress: SchemaLinkProgress | None = None,
) -> list[InferredLink]:
    table_by_name = {table.name: table for table in tables}
    declared_pairs = get_declared_column_pairs(declared_links)

    triaged_refs = get_triaged_refs(column_refs, options)
    name_candidates = get_name_candidates(
        conn, table_by_name, triaged_refs, declared_pairs, options
    )
    candidate_columns = get_distinct_candidate_columns(
        triaged_refs, name_candidates, options
    )

    distinct_sets = load_distinct_sets(
        conn,
        table_by_name,
        column_refs,
        candidate_columns,
        options.max_distinct_values,
        progress,
    )
    lsh_candidates = get_lsh_candidates(
        triaged_refs, distinct_sets, declared_pairs, options
    )
    candidates = merge_candidates(name_candidates + lsh_candidates)

    links: dict[frozenset[tuple[str, str]], InferredLink] = {}
    for candidate in candidates:
        left_values = distinct_sets.get(candidate.left.key)
        right_values = distinct_sets.get(candidate.right.key)
        if not left_values or not right_values:
            continue
        for source, target, source_values, target_values in (
            (candidate.left, candidate.right, left_values, right_values),
            (candidate.right, candidate.left, right_values, left_values),
        ):
            containment = len(source_values & target_values) / len(source_values)
            if containment < options.containment_threshold:
                continue
            if not plausible_direction(source, target, candidate.evidence):
                continue
            evidence = tuple(
                sorted(
                    set(candidate.evidence)
                    | set(get_cardinality_evidence(source, target, options))
                )
            )
            if len(evidence) < 3:
                continue
            key = frozenset({source.key, target.key})
            notes = tuple(sorted(get_notes(source, target, options)))
            link = InferredLink(source, target, containment, evidence, notes)
            existing = links.get(key)
            if existing is None or link_rank_key(link) < link_rank_key(existing):
                links[key] = link

    return sorted(links.values(), key=link_rank_key)


def get_declared_column_pairs(
    declared_links: list[DeclaredLink],
) -> set[frozenset[tuple[str, str]]]:
    pairs: set[frozenset[tuple[str, str]]] = set()
    for link in declared_links:
        for from_column, to_column in zip(
            link.from_columns, link.to_columns, strict=False
        ):
            pairs.add(
                frozenset(
                    {
                        (link.from_table, from_column),
                        (link.to_table, to_column),
                    }
                )
            )
    return pairs


def get_distinct_candidate_columns(
    column_refs: dict[tuple[str, str], ColumnRef],
    name_candidates: list[CandidatePair],
    options: SchemaLinkOptions,
) -> set[tuple[str, str]]:
    candidate_columns = {candidate.left.key for candidate in name_candidates} | {
        candidate.right.key for candidate in name_candidates
    }
    for ref in column_refs.values():
        if is_primary_lsh_target(ref, options):
            candidate_columns.add(ref.key)
    return candidate_columns


def get_triaged_refs(
    column_refs: dict[tuple[str, str], ColumnRef],
    options: SchemaLinkOptions,
) -> dict[tuple[str, str], ColumnRef]:
    refs: dict[tuple[str, str], ColumnRef] = {}
    for key, ref in column_refs.items():
        if (
            ref.cardinality_ratio >= options.unique_drop_ratio
            and not ref.is_primary_or_unique
            and not ref.is_id_like
        ):
            continue
        refs[key] = ref
    return refs


def get_name_candidates(
    conn: Connection,
    table_by_name: dict[str, Table],
    column_refs: dict[tuple[str, str], ColumnRef],
    declared_pairs: set[frozenset[tuple[str, str]]],
    options: SchemaLinkOptions,
) -> list[CandidatePair]:
    refs = sorted(column_refs.values(), key=lambda ref: ref.key)
    candidates: list[CandidatePair] = []
    for index, left in enumerate(refs):
        for right in refs[index + 1 :]:
            if left.table == right.table or left.type_group != right.type_group:
                continue
            if frozenset({left.key, right.key}) in declared_pairs:
                continue
            name_evidence = get_name_evidence(left, right)
            if not name_evidence:
                continue
            evidence = tuple(
                dict.fromkeys(
                    name_evidence
                    + get_cardinality_evidence(left, right, options)
                    + ("type match",)
                )
            )
            if is_strong_name_candidate(evidence) and not spot_check_overlap(
                conn, table_by_name, left, right
            ):
                continue
            candidates.append(CandidatePair(left, right, evidence))
    return candidates


def load_distinct_sets(
    conn: Connection,
    table_by_name: dict[str, Table],
    column_refs: dict[tuple[str, str], ColumnRef],
    candidate_columns: set[tuple[str, str]],
    max_distinct_values: int,
    progress: SchemaLinkProgress | None = None,
) -> dict[tuple[str, str], set[Any]]:
    distinct_sets: dict[tuple[str, str], set[Any]] = {}
    sorted_candidate_columns = sorted(candidate_columns)
    for index, key in enumerate(sorted_candidate_columns, start=1):
        ref = column_refs[key]
        if progress is not None:
            progress(
                index - 1,
                len(sorted_candidate_columns),
                f"loading {ref.label}",
            )
        if ref.distinct_count > max_distinct_values:
            if progress is not None:
                progress(
                    index,
                    len(sorted_candidate_columns),
                    f"skipped {ref.label}",
                )
            continue
        table = table_by_name[ref.table]
        column = table.c[ref.column]
        try:
            values = {
                normalize_value(row[0])
                for row in query_timeout.execute(
                    conn, select(column).where(column.is_not(None)).distinct()
                )
                if normalize_value(row[0]) is not None
            }
        except query_timeout.QueryTimeout:
            values = set()
        if values:
            distinct_sets[key] = values
        if progress is not None:
            progress(
                index,
                len(sorted_candidate_columns),
                f"loaded {ref.label}",
            )
    return distinct_sets


def get_lsh_candidates(
    column_refs: dict[tuple[str, str], ColumnRef],
    distinct_sets: dict[tuple[str, str], set[Any]],
    declared_pairs: set[frozenset[tuple[str, str]]],
    options: SchemaLinkOptions,
) -> list[CandidatePair]:
    if len(distinct_sets) < 2:
        return []

    minhashes: dict[tuple[str, str], MinHash] = {}
    for key, values in distinct_sets.items():
        minhash = MinHash(num_perm=options.minhash_permutations)
        for value in sorted(values, key=stable_sort_value):
            minhash.update(stable_hash_value(value))
        minhashes[key] = minhash

    ensemble = MinHashLSHEnsemble(
        threshold=options.containment_threshold,
        num_perm=options.minhash_permutations,
    )
    ensemble.index(
        (key, minhashes[key], len(distinct_sets[key])) for key in sorted(minhashes)
    )

    candidates: list[CandidatePair] = []
    for left_key, minhash in sorted(minhashes.items()):
        for right_key in ensemble.query(minhash, len(distinct_sets[left_key])):
            if left_key == right_key:
                continue
            first_key, second_key = sorted([left_key, right_key])
            left = column_refs[first_key]
            right = column_refs[second_key]
            if left.table == right.table or left.type_group != right.type_group:
                continue
            if frozenset({left.key, right.key}) in declared_pairs:
                continue
            candidates.append(
                CandidatePair(left, right, ("minhash containment candidate",))
            )
    return candidates


def merge_candidates(candidates: list[CandidatePair]) -> list[CandidatePair]:
    merged: dict[frozenset[tuple[str, str]], CandidatePair] = {}
    for candidate in candidates:
        key = frozenset({candidate.left.key, candidate.right.key})
        existing = merged.get(key)
        if existing is None:
            merged[key] = candidate
            continue
        evidence = tuple(sorted(set(existing.evidence) | set(candidate.evidence)))
        merged[key] = CandidatePair(existing.left, existing.right, evidence)
    return sorted(
        merged.values(),
        key=lambda candidate: (candidate.left.key, candidate.right.key),
    )


def link_rank_key(
    link: InferredLink,
) -> tuple[int, float, str, str, str, str]:
    return (
        -len(link.evidence),
        -link.containment,
        link.source.table,
        link.source.column,
        link.target.table,
        link.target.column,
    )
