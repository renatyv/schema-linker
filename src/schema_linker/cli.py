from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from sqlalchemy import create_engine

from schema_linker.connection import (
    add_connection_arguments,
    list_schemas,
    resolve_database_url,
    resolve_schema,
)
from schema_linker.core import link_schema
from schema_linker.models import SchemaLinkOptions
from schema_linker.progress import ProgressBar
from schema_linker.query_timeout import DEFAULT_QUERY_TIMEOUT
from schema_linker.shared import default_output_path, output_component, parse_table_set


def build_arg_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Markdown schema join links for a database.",
        prog=prog,
    )
    add_connection_arguments(parser)
    parser.add_argument("--output", help="Output directory. Defaults to <database>/.")
    parser.add_argument("--include-tables", help="Comma-separated table allowlist.")
    parser.add_argument("--exclude-tables", help="Comma-separated table denylist.")
    parser.add_argument(
        "--include-technical-tables",
        action="store_true",
        help=(
            "Link migration/framework tables (e.g. schema_migrations, "
            "alembic_version, flyway_schema_history) that are skipped by default."
        ),
    )
    parser.add_argument(
        "--show-evidence",
        action="store_true",
        help=(
            "Include evidence labels on inferred links. Omitted by default to "
            "save tokens."
        ),
    )
    parser.add_argument(
        "--show-declared-links",
        action="store_true",
        help=(
            "Include the Declared PK/FK Links section. Omitted by default to "
            "save tokens; declared links are still used to group inferred links."
        ),
    )
    parser.add_argument(
        "--containment-threshold",
        type=float,
        default=0.8,
        help="Minimum exact containment for inferred links.",
    )
    parser.add_argument(
        "--max-distinct-values",
        type=int,
        default=10_000,
        help="Maximum distinct values to load per candidate column.",
    )
    parser.add_argument(
        "--query-timeout",
        type=int,
        default=DEFAULT_QUERY_TIMEOUT,
        help=(
            "Abort any linking query that runs longer than this many seconds, skip the affected "
            "column/metric, and continue. 0 disables. Applies to PostgreSQL/MySQL/MariaDB "
            f"(SQLite/DuckDB have no native support). Default {DEFAULT_QUERY_TIMEOUT}."
        ),
    )
    return parser


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
    parser = build_arg_parser(prog=prog)
    args = parser.parse_args(argv)
    if args.query_timeout < 0:
        parser.error("--query-timeout must be a non-negative integer")
    url = resolve_database_url(args, parser)

    options = SchemaLinkOptions(
        include_tables=parse_table_set(args.include_tables),
        exclude_tables=parse_table_set(args.exclude_tables) or frozenset(),
        containment_threshold=args.containment_threshold,
        max_distinct_values=args.max_distinct_values,
        query_timeout=args.query_timeout,
        schema=resolve_schema(args),
        include_technical_tables=args.include_technical_tables,
        show_evidence=args.show_evidence,
        show_declared_links=args.show_declared_links,
    )
    engine = create_engine(url)
    progress_bar = ProgressBar("Linking", 0)
    active_schema = ""

    def show_progress(current: int, total: int, item: str) -> None:
        nonlocal progress_bar
        item = f"{active_schema}: {item}"
        if progress_bar.total != total:
            progress_bar.finish()
            progress_bar = ProgressBar("Linking", total)
            progress_bar.start(item)
            return
        progress_bar.update(current, item)

    schemas = list_schemas(engine, options.schema)
    output_dir = (
        Path(args.output)
        if args.output
        else default_output_path(args.database or os.environ["SCHEMA_LINKER_DATABASE"])
    )
    try:
        for schema in schemas:
            active_schema = schema
            schema_options = replace(options, schema=schema)
            output = link_schema(engine, schema_options, progress=show_progress)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{output_component(schema)}_schema_links.md").write_text(
                output, encoding="utf-8"
            )
    except Exception:
        progress_bar.finish()
        raise
    else:
        progress_bar.finish("Schema linking complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
