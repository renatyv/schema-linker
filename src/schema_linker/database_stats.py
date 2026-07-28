from __future__ import annotations

from sqlalchemy import Table, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import UniqueConstraint

# Tables whose catalog row estimate is at/above this count are profiled from
# internal database stats only: COUNT(*) and all per-column aggregations are
# skipped because they would be far too slow. "Hundreds of millions or more".
LARGE_TABLE_THRESHOLD = 100_000_000


def estimate_row_count(conn: Connection, table: Table) -> int | None:
    """Return a cheap catalog row-count estimate, or ``None`` if unavailable.

    Used to decide whether a full ``COUNT(*)`` scan is affordable. Any failure
    (missing stats table, stale/unknown marker, parse error) collapses to
    ``None`` so the caller falls back to an exact count.
    """
    dialect = conn.dialect.name
    schema = table.schema or conn.dialect.default_schema_name
    try:
        if dialect == "postgresql":
            return _postgres_row_estimate(conn, table.name, schema)
        if dialect in {"mysql", "mariadb"}:
            return _mysql_row_estimate(conn, table.name, schema)
        if dialect == "duckdb":
            return _duckdb_row_estimate(conn, table.name, schema)
        if dialect == "sqlite":
            return _sqlite_row_estimate(conn, table.name)
    except SQLAlchemyError:
        return None
    return None


def _postgres_row_estimate(
    conn: Connection, table_name: str, schema: str | None
) -> int | None:
    row = conn.execute(
        text(
            "SELECT c.reltuples::bigint FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = :table AND n.nspname = :schema"
        ),
        {"table": table_name, "schema": schema or "public"},
    ).one_or_none()
    if not row or row[0] is None or int(row[0]) < 0:
        return None
    return int(row[0])


def _mysql_row_estimate(
    conn: Connection, table_name: str, schema: str | None
) -> int | None:
    schema_name = schema or conn.dialect.default_schema_name
    if not schema_name:
        return None
    value = conn.execute(
        text(
            "SELECT TABLE_ROWS FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table"
        ),
        {"schema": schema_name, "table": table_name},
    ).scalar_one_or_none()
    if value is None:
        return None
    return int(value)


def _duckdb_row_estimate(
    conn: Connection, table_name: str, schema: str | None
) -> int | None:
    schema_name = schema or "main"
    value = conn.execute(
        text(
            "SELECT estimated_size FROM duckdb_tables() "
            "WHERE schema_name = :schema AND table_name = :table"
        ),
        {"schema": schema_name, "table": table_name},
    ).scalar_one_or_none()
    if value is None or int(value) < 0:
        return None
    return int(value)


def _sqlite_row_estimate(conn: Connection, table_name: str) -> int | None:
    # sqlite_stat1 only exists after ANALYZE. The stat string is "N d1 d2 ..."
    # where N is the estimated number of rows in the table.
    stat = conn.execute(
        text("SELECT stat FROM sqlite_stat1 WHERE tbl = :table LIMIT 1"),
        {"table": table_name},
    ).scalar_one_or_none()
    if not stat:
        return None
    first = str(stat).split()[0]
    try:
        count = int(first)
    except ValueError:
        return None
    return count if count >= 0 else None


def get_indexed_column_names(table: Table) -> set[str]:
    indexed = {column.name for column in table.primary_key.columns}
    for index in table.indexes:
        indexed.update(column.name for column in index.columns)
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            indexed.update(column.name for column in constraint.columns)
    return indexed
