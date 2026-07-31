from __future__ import annotations

from typing import Any

from sqlalchemy import Table, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.sql.sqltypes import (
    BigInteger,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
)

from schema_linker import query_timeout
from schema_linker.database_stats import (
    LARGE_TABLE_THRESHOLD,
    estimate_row_count,
    get_indexed_column_names,
)
from schema_linker.models import (
    ColumnRef,
    DeclaredLink,
    SchemaLinkOptions,
    SchemaLinkProgress,
)
from schema_linker.shared import is_sensitive


def collect_declared_links(
    tables: list[Table], selected_tables: set[str]
) -> list[DeclaredLink]:
    links: list[DeclaredLink] = []
    for table in tables:
        for constraint in sorted(
            table.foreign_key_constraints,
            key=lambda item: constraint_sort_key(item.elements),
        ):
            if constraint.referred_table.name not in selected_tables:
                continue
            from_columns = tuple(element.parent.name for element in constraint.elements)
            to_columns = tuple(element.column.name for element in constraint.elements)
            links.append(
                DeclaredLink(
                    table.name,
                    from_columns,
                    constraint.referred_table.name,
                    to_columns,
                )
            )
    return sorted(
        links,
        key=lambda link: (
            link.from_table,
            link.from_columns,
            link.to_table,
            link.to_columns,
        ),
    )


def constraint_sort_key(elements: Any) -> tuple[str, ...]:
    return tuple(element.parent.name for element in elements)


def collect_column_refs(
    conn: Connection,
    tables: list[Table],
    options: SchemaLinkOptions,
    progress: SchemaLinkProgress | None = None,
) -> dict[tuple[str, str], ColumnRef]:
    refs: dict[tuple[str, str], ColumnRef] = {}
    row_counts = _load_row_counts(conn, tables)
    for index, table in enumerate(tables, start=1):
        if progress is not None:
            progress(index - 1, len(tables), f"inspecting {table.name}")
        total_rows = row_counts[table.name]
        unique_columns = get_unique_column_names(table)
        indexed_columns = get_indexed_column_names(table)
        for column in table.columns:
            if is_sensitive(column.name):
                continue
            type_group = get_type_group(column)
            if type_group == "other":
                continue
            ref = _build_column_ref(
                conn,
                table,
                column,
                total_rows,
                type_group,
                unique_columns,
                indexed_columns,
            )
            if ref is not None:
                refs[ref.key] = ref
        if progress is not None:
            progress(index, len(tables), f"inspected {table.name}")
    return refs


def _load_row_counts(conn: Connection, tables: list[Table]) -> dict[str, int | None]:
    """Cheap row counts per table, using catalog estimates for very large tables.

    Returns ``None`` for a table whose exact COUNT(*) is unavailable (timed out).
    """
    row_counts: dict[str, int | None] = {}
    for table in tables:
        estimate = estimate_row_count(conn, table)
        if estimate is not None and estimate >= LARGE_TABLE_THRESHOLD:
            row_counts[table.name] = estimate
            continue
        try:
            row_counts[table.name] = int(
                query_timeout.execute(
                    conn, select(func.count()).select_from(table)
                ).scalar_one()
            )
        except query_timeout.QueryTimeout:
            row_counts[table.name] = None
        except Exception:
            query_timeout.recover_connection(conn)
            row_counts[table.name] = None
    return row_counts


def _build_column_ref(
    conn: Connection,
    table: Table,
    column: Any,
    total_rows: int | None,
    type_group: str,
    unique_columns: set[str],
    indexed_columns: set[str],
) -> ColumnRef | None:
    """Build a ColumnRef for a column, applying row-count gates and skipping on timeout.

    Gates mirror the profiler: COUNT(column) only when total_rows <= 5M (or indexed),
    COUNT(DISTINCT column) only when total_rows <= 100K (or <= 1M and indexed).
    """
    if total_rows is None:
        return None
    indexed = column.name in indexed_columns
    if not (total_rows <= 5_000_000 or indexed):
        return None
    try:
        non_nulls = int(
            query_timeout.execute(
                conn, select(func.count(column)).select_from(table)
            ).scalar_one()
        )
    except query_timeout.QueryTimeout:
        return None
    except Exception:
        query_timeout.recover_connection(conn)
        return None
    if non_nulls == 0:
        return None
    if not (total_rows <= 100_000 or (total_rows <= 1_000_000 and indexed)):
        return None
    try:
        distinct_count = int(
            query_timeout.execute(
                conn, select(func.count(func.distinct(column))).select_from(table)
            ).scalar_one()
        )
    except query_timeout.QueryTimeout:
        return None
    except Exception:
        query_timeout.recover_connection(conn)
        return None
    return ColumnRef(
        table=table.name,
        column=column.name,
        type_group=type_group,
        is_primary_or_unique=column.name in unique_columns,
        is_id_like=is_id_like(column.name),
        total_rows=total_rows,
        non_nulls=non_nulls,
        distinct_count=distinct_count,
    )


def get_unique_column_names(table: Table) -> set[str]:
    unique_columns = {column.name for column in table.primary_key.columns}
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and len(constraint.columns) == 1:
            unique_columns.update(column.name for column in constraint.columns)
    for index in table.indexes:
        if index.unique and len(index.columns) == 1:
            unique_columns.update(column.name for column in index.columns)
    return unique_columns


def get_type_group(column: Any) -> str:
    column_type = column.type
    if isinstance(column_type, (Integer, BigInteger, SmallInteger, Numeric, Float)):
        return "numeric"
    if isinstance(column_type, (String, Text)):
        return "string"
    if isinstance(column_type, (Date, DateTime, Time)):
        return "datetime"
    return "other"


def is_id_like(column_name: str) -> bool:
    lower_name = column_name.lower()
    return lower_name == "id" or lower_name.endswith("_id") or lower_name.endswith("id")
