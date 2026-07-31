from __future__ import annotations

import logging

from sqlalchemy import MetaData, Table, inspect
from sqlalchemy.engine import Engine

from schema_linker import query_timeout
from schema_linker.inference import infer_links
from schema_linker.metadata import (
    collect_column_refs,
    collect_declared_links,
)
from schema_linker.models import SchemaLinkOptions, SchemaLinkProgress
from schema_linker.permissions import check_permissions, format_warnings
from schema_linker.rendering import render_markdown
from schema_linker.shared import is_technical_table

_logger = logging.getLogger("schema_linker")


def link_schema(
    engine: Engine,
    options: SchemaLinkOptions,
    progress: SchemaLinkProgress | None = None,
) -> str:
    inspector = inspect(engine)
    table_names = sorted(inspector.get_table_names(schema=options.schema))
    if not options.include_technical_tables:
        table_names = [table for table in table_names if not is_technical_table(table)]
    if options.include_tables is not None:
        table_names = [
            table for table in table_names if table in options.include_tables
        ]
    table_names = [
        table for table in table_names if table not in options.exclude_tables
    ]

    url = engine.url.render_as_string(hide_password=True)
    database = engine.url.database or ""

    with engine.connect() as conn:
        query_timeout.apply_query_timeout(conn, options.query_timeout)
        perm_report = check_permissions(
            conn, engine.dialect.name, options.schema, table_names
        )
        for warning in format_warnings(perm_report):
            _logger.warning(warning)
        accessible = set(perm_report.accessible_tables)
        table_names = [name for name in table_names if name in accessible]
        if not table_names:
            _logger.warning("No accessible tables to link; skipping schema.")
            return render_markdown(
                engine.dialect.name,
                database,
                options.schema or engine.dialect.default_schema_name or "",
                url,
                [],
                [],
                show_evidence=options.show_evidence,
                show_declared_links=options.show_declared_links,
            )
        metadata = MetaData()
        tables = []
        for index, table_name in enumerate(table_names, start=1):
            if progress is not None:
                progress(index - 1, len(table_names), f"reflecting {table_name}")
            tables.append(
                Table(
                    table_name,
                    metadata,
                    schema=options.schema,
                    autoload_with=conn,
                )
            )
            if progress is not None:
                progress(index, len(table_names), f"reflected {table_name}")
        declared_links = collect_declared_links(tables, set(table_names))
        column_refs = collect_column_refs(conn, tables, options, progress)
        inferred_links = infer_links(
            conn,
            tables,
            column_refs,
            declared_links,
            options,
            progress,
        )

    return render_markdown(
        engine.dialect.name,
        database,
        options.schema or engine.dialect.default_schema_name or "",
        url,
        declared_links,
        inferred_links,
        show_evidence=options.show_evidence,
        show_declared_links=options.show_declared_links,
    )
