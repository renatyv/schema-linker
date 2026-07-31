from __future__ import annotations

import re

from schema_linker import __version__
from schema_linker.inference import link_rank_key
from schema_linker.models import DeclaredLink, InferredLink


def render_markdown(
    dialect: str,
    database: str,
    schema: str,
    url: str,
    declared_links: list[DeclaredLink],
    inferred_links: list[InferredLink],
    show_evidence: bool = False,
    show_declared_links: bool = False,
) -> str:
    lines = [
        "# Schema Links",
        "",
        f"- version: {__version__}",
        f"- dialect: {dialect}",
        f"- database: {database}",
        f"- schema: {schema}",
    ]
    if show_declared_links:
        lines += ["", "## Declared PK/FK Links", ""]
        if declared_links:
            for link in declared_links:
                from_label = ", ".join(
                    f"{link.from_table}.{column}" for column in link.from_columns
                )
                to_label = ", ".join(
                    f"{link.to_table}.{column}" for column in link.to_columns
                )
                lines.append(f"{from_label} -> {to_label}")
        else:
            lines.append("No declared PK/FK links found.")

    lines += ["", "## Inferred Links", ""]
    lines.extend(render_inferred_section(declared_links, inferred_links, show_evidence))

    return "\n".join(lines).rstrip() + "\n"


def render_inferred_section(
    declared_links: list[DeclaredLink],
    inferred_links: list[InferredLink],
    show_evidence: bool,
) -> list[str]:
    """Render inferred links grouped by shared value domain.

    Columns that join to the same primary key (or simply share a value set) form
    one connected component. Within a component we distinguish columns already
    covered by a declared FK (context only) from genuinely new inferred columns
    (the signal). Components whose every column is already declared add no new
    information and are omitted.
    """
    if not inferred_links:
        return ["No inferred links found."]

    fk_nodes, pk_nodes = _declared_nodes(declared_links)

    edges: list[tuple[str, str]] = []
    for link in declared_links:
        for from_column, to_column in zip(
            link.from_columns, link.to_columns, strict=False
        ):
            edges.append(
                (f"{link.from_table}.{from_column}", f"{link.to_table}.{to_column}")
            )
    for link in inferred_links:
        edges.append((link.source.label, link.target.label))

    known = fk_nodes | pk_nodes
    blocks: list[tuple[int, str, list[str]]] = []
    for members in _connected_components(edges):
        member_set = set(members)
        cluster_links = [
            link
            for link in inferred_links
            if link.source.label in member_set and link.target.label in member_set
        ]
        if not cluster_links:
            continue
        new_members = sorted(member_set - known)
        if not new_members:
            # Every column is already a declared FK/PK, so the inferred edges
            # are fully implied by the declared relationships above.
            continue
        anchor = next((node for node in sorted(member_set) if node in pk_nodes), None)
        declared_members = sorted(
            (member_set & fk_nodes) - ({anchor} if anchor else set())
        )
        heading = anchor if anchor else _domain_label(sorted(member_set))

        block = [f"### {heading}"]
        if show_evidence:
            block.append("- inferred:")
            for member in new_members:
                evidence = _best_evidence_for(member, cluster_links)
                suffix = f": {', '.join(evidence)}" if evidence else ""
                block.append(f"  - {member}{suffix}")
        else:
            block.append(f"- inferred: {', '.join(new_members)}")
        if declared_members:
            block.append(f"- declared: {', '.join(declared_members)}")
        blocks.append((-len(new_members), heading, block))

    if not blocks:
        return ["All inferred links are implied by the declared PK/FK links above."]

    blocks.sort(key=lambda item: (item[0], item[1]))
    lines: list[str] = []
    for _, _, block in blocks:
        lines.extend(block)
        lines.append("")
    return lines[:-1] if lines else []


def _best_evidence_for(
    member: str, cluster_links: list[InferredLink]
) -> tuple[str, ...]:
    """Evidence from the strongest inferred edge touching ``member``.

    Evidence is pairwise, so attaching one edge's evidence to a specific
    column keeps it meaningful and avoids merging mutually-exclusive
    cardinality labels (low vs. moderate) across the whole cluster.
    """
    touching = [
        link
        for link in cluster_links
        if link.source.label == member or link.target.label == member
    ]
    if not touching:
        return ()
    return min(touching, key=link_rank_key).evidence


def _declared_nodes(
    declared_links: list[DeclaredLink],
) -> tuple[set[str], set[str]]:
    fk_nodes: set[str] = set()
    pk_nodes: set[str] = set()
    for link in declared_links:
        for column in link.from_columns:
            fk_nodes.add(f"{link.from_table}.{column}")
        for column in link.to_columns:
            pk_nodes.add(f"{link.to_table}.{column}")
    return fk_nodes, pk_nodes


def _connected_components(edges: list[tuple[str, str]]) -> list[set[str]]:
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    for left, right in edges:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[left_root] = right_root

    components: dict[str, set[str]] = {}
    for node in parent:
        components.setdefault(find(node), set()).add(node)
    return list(components.values())


def _tokens(label: str) -> set[str]:
    """Lowercase alphanumeric tokens of a "table.column" label, minus noise."""
    return {
        token
        for token in re.split(r"[^a-z0-9]+", label.lower())
        if token and token != "id"
    }


def _domain_label(members: list[str]) -> str:
    """Derive a short label for a cluster with no declared primary key.

    Prefers a column-name token shared by every member, then the most frequent
    shared token, and finally falls back to a generic label.
    """
    per_member: list[set[str]] = []
    counts: dict[str, int] = {}
    for member in members:
        tokens = _tokens(member)
        per_member.append(tokens)
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1

    common = set.intersection(*per_member) if per_member else set()
    if common:
        return max(common, key=lambda token: (counts[token], token))
    if counts:
        best = max(counts.values())
        if best >= 2:
            winners = [token for token in counts if counts[token] == best]
            return max(winners)
    return "shared values"
