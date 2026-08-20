from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import Table, select
from sqlalchemy.engine import Connection

from schema_linker import query_timeout
from schema_linker.models import ColumnRef, SchemaLinkOptions


def plausible_direction(
    source: ColumnRef, target: ColumnRef, evidence: tuple[str, ...]
) -> bool:
    if source.is_primary_or_unique and target.is_primary_or_unique:
        return False
    if (
        not has_name_signal(evidence)
        and source.type_group == "numeric"
        and (source.is_id_like or target.is_id_like)
    ):
        return False
    if target.is_primary_or_unique and not source.is_primary_or_unique:
        return True
    if source.is_id_like and not target.is_id_like:
        return True
    if "name match" in evidence or "table-name id match" in evidence:
        return (
            target.is_primary_or_unique
            or target.column.lower() == "id"
            or source.is_id_like
        )
    return not source.is_primary_or_unique or target.is_primary_or_unique


def has_name_signal(evidence: tuple[str, ...]) -> bool:
    return any(
        item in evidence
        for item in (
            "name match",
            "table-name id match",
            "shared name tokens",
            "similar names",
        )
    )


def get_notes(
    source: ColumnRef, target: ColumnRef, options: SchemaLinkOptions
) -> list[str]:
    notes: list[str] = []
    if is_low_cardinality(source, options) or is_low_cardinality(target, options):
        notes.append("low cardinality")
    else:
        notes.append("moderate cardinality")
    if target.is_primary_or_unique:
        notes.append("target primary/unique")
    return notes


def get_cardinality_evidence(
    left: ColumnRef, right: ColumnRef, options: SchemaLinkOptions
) -> tuple[str, ...]:
    evidence: list[str] = []
    if left.distinct_count == right.distinct_count:
        evidence.append("same distinct count")
    elif (
        min(left.distinct_count, right.distinct_count)
        / max(left.distinct_count, right.distinct_count)
        >= 0.8
    ):
        evidence.append("similar distinct counts")
    if is_low_cardinality(left, options) or is_low_cardinality(right, options):
        evidence.append("low cardinality")
    elif left.is_id_like or right.is_id_like:
        evidence.append("moderate ID-like cardinality")
    else:
        evidence.append("moderate cardinality")
    return tuple(evidence)


def get_name_evidence(left: ColumnRef, right: ColumnRef) -> tuple[str, ...]:
    left_name = normalize_name(left.column)
    right_name = normalize_name(right.column)
    left_tokens = name_tokens(left.column)
    right_tokens = name_tokens(right.column)
    left_table = singularize(normalize_name(left.table))
    right_table = singularize(normalize_name(right.table))

    evidence: list[str] = []
    if left_name == right_name and left_name != "id":
        evidence.append("name match")
    if (left_table in right_tokens and left.column.lower() == "id") or (
        right_table in left_tokens and right.column.lower() == "id"
    ):
        evidence.append("table-name id match")
    if left_tokens & right_tokens and left_tokens & right_tokens != {"id"}:
        evidence.append("shared name tokens")
    if (
        SequenceMatcher(None, left_name, right_name).ratio() >= 0.82
        and left_name != "id"
        and right_name != "id"
    ):
        evidence.append("similar names")
    return tuple(dict.fromkeys(evidence))


def is_primary_lsh_target(ref: ColumnRef, options: SchemaLinkOptions) -> bool:
    return ref.is_id_like and not is_low_cardinality(ref, options)


def is_strong_name_candidate(evidence: tuple[str, ...]) -> bool:
    return (
        len(
            set(evidence)
            & {
                "name match",
                "table-name id match",
                "shared name tokens",
                "similar names",
            }
        )
        >= 2
    )


def spot_check_overlap(
    conn: Connection,
    table_by_name: dict[str, Table],
    left: ColumnRef,
    right: ColumnRef,
    limit: int = 50,
) -> bool:
    try:
        left_values = load_limited_distinct_values(
            conn, table_by_name[left.table], left.column, limit
        )
        right_values = load_limited_distinct_values(
            conn, table_by_name[right.table], right.column, limit
        )
    except query_timeout.QueryTimeout:
        return True
    if not left_values or not right_values:
        return False
    return bool(left_values & right_values)


def load_limited_distinct_values(
    conn: Connection, table: Table, column_name: str, limit: int
) -> set[Any]:
    column = table.c[column_name]
    values = set()
    for row in query_timeout.execute(
        conn,
        select(column).where(column.is_not(None)).distinct().limit(limit),
    ):
        value = normalize_value(row[0])
        if value is not None:
            values.add(value)
    return values


def is_low_cardinality(ref: ColumnRef, options: SchemaLinkOptions) -> bool:
    return (
        ref.cardinality_ratio <= options.low_cardinality_ratio
        or ref.distinct_count <= 3
    )


_FLAG_VALUES = frozenset(
    {"0", "1", "y", "n", "t", "f", "true", "false", "yes", "no"}
)


def is_flag_like(ref: ColumnRef, values: set[Any] | None) -> bool:
    """True when a column looks like a boolean/flag domain.

    Either it holds at most two distinct values, or every loaded value is a
    boolean-ish string (0/1, Y/N, true/false, yes/no).
    """
    if ref.distinct_count <= 2:
        return True
    if values is None:
        return False
    return all(
        isinstance(value, str) and value.lower() in _FLAG_VALUES for value in values
    )


def is_flag_pair(
    left: ColumnRef,
    right: ColumnRef,
    left_values: set[Any] | None,
    right_values: set[Any] | None,
) -> bool:
    """True when both sides are boolean/flag columns and neither side is a key.

    Joining two independent Y/N flags is a cross-product trap rather than a
    join path, so such pairs are dropped — unless one side is primary/unique
    (a two-row lookup table's key column legitimately has 1-2 values).
    """
    if left.is_primary_or_unique or right.is_primary_or_unique:
        return False
    return is_flag_like(left, left_values) and is_flag_like(right, right_values)


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


# "sname"-style abbreviations: one letter + a common join-column word.
_ABBREVIATED_TOKEN = re.compile(r"^[a-z](?P<suffix>name|code)$")


def name_tokens(value: str) -> set[str]:
    tokens = {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token}
    normalized = normalize_name(value)
    if normalized.endswith("id") and normalized != "id":
        tokens.add(normalized[:-2])
        tokens.add("id")
    # Expand single-letter abbreviations of common join-column words so that
    # e.g. "sname" ("school name") still shares a token with "School Name".
    for token in tuple(tokens):
        match = _ABBREVIATED_TOKEN.match(token)
        if match:
            tokens.add(match.group("suffix"))
    return {singularize(token) for token in tokens if token}


def singularize(value: str) -> str:
    if value.endswith("ies") and len(value) > 3:
        return value[:-3] + "y"
    if value.endswith("s") and len(value) > 1:
        return value[:-1]
    return value


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value


def stable_sort_value(value: Any) -> tuple[str, str]:
    return (type(value).__name__, str(value))


def stable_hash_value(value: Any) -> bytes:
    value_type, rendered = stable_sort_value(value)
    return f"{value_type}:{rendered}".encode("utf-8")
