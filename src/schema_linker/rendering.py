from __future__ import annotations

from schema_linker import __version__
from schema_linker.models import DeclaredLink, InferredLink


def render_markdown(
    dialect: str,
    database: str,
    schema: str,
    url: str,
    declared_links: list[DeclaredLink],
    inferred_links: list[InferredLink],
) -> str:
    lines = [
        "# Schema Links",
        "",
        f"- version: {__version__}",
        f"- dialect: {dialect}",
        f"- database: {database}",
        f"- schema: {schema}",
        "",
        "## Declared PK/FK Links",
        "",
    ]
    if declared_links:
        lines.extend(
            [
                "| From | To |",
                "|---|---|",
            ]
        )
        for link in declared_links:
            from_label = ", ".join(
                f"{link.from_table}.{column}" for column in link.from_columns
            )
            to_label = ", ".join(
                f"{link.to_table}.{column}" for column in link.to_columns
            )
            lines.append(
                f"| {markdown_cell(from_label)} | {markdown_cell(to_label)} |"
            )
    else:
        lines.append("No declared PK/FK links found.")

    lines.extend(["", "## Inferred Links", ""])
    if inferred_links:
        lines.extend(
            [
                "| From | To | Evidence |",
                "|---|---|---|",
            ]
        )
        for link in inferred_links:
            evidence = ", ".join(link.evidence)
            lines.append(
                f"| {markdown_cell(link.source.label)} | "
                f"{markdown_cell(link.target.label)} | "
                f"{markdown_cell(evidence)} |"
            )
    else:
        lines.append("No inferred links found.")

    return "\n".join(lines).rstrip() + "\n"


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")
