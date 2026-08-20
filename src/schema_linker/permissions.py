from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

_logger = logging.getLogger("schema_linker")


@dataclass(frozen=True)
class PermissionReport:
    dialect: str
    schema: str | None
    accessible_tables: list[str]
    inaccessible_tables: list[tuple[str, str]]
    stats_access: dict[str, bool]

    @property
    def has_select_access(self) -> bool:
        return len(self.accessible_tables) > 0


def check_permissions(
    conn: Connection,
    dialect: str,
    schema: str | None,
    table_names: list[str],
) -> PermissionReport:
    """Probe the connected user's privileges before profiling or linking.

    Checks three things:
      1. Table discovery (implicitly confirmed if *table_names* is non-empty).
      2. SELECT access on each user table.
      3. Read access to the internal catalog/stats views the profiler relies on.
    """
    if dialect == "postgresql":
        accessible, inaccessible = _check_postgres_tables(conn, schema, table_names)
        stats = _check_postgres_stats(conn)
    elif dialect in {"mysql", "mariadb"}:
        accessible, inaccessible = _check_mysql_tables(conn, schema, table_names)
        stats = _check_mysql_stats(conn)
    elif dialect == "duckdb":
        accessible = list(table_names)
        inaccessible = []
        stats = {
            "duckdb_tables": _probe_success(
                conn, "SELECT 1 FROM duckdb_tables() LIMIT 1"
            )
        }
    else:
        accessible = list(table_names)
        inaccessible = []
        stats = {"sqlite_stat1": _check_table_exists(conn, "sqlite_stat1")}

    return PermissionReport(
        dialect=dialect,
        schema=schema,
        accessible_tables=accessible,
        inaccessible_tables=inaccessible,
        stats_access=stats,
    )


def _check_postgres_tables(
    conn: Connection,
    schema: str | None,
    table_names: list[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    if not table_names:
        return [], []
    schema_name = schema or conn.dialect.default_schema_name or "public"
    accessible: list[str] = []
    inaccessible: list[tuple[str, str]] = []
    for table_name in table_names:
        qualified = f"{schema_name}.{table_name}"
        try:
            with conn.begin_nested():
                can = conn.execute(
                    text("SELECT has_table_privilege(current_user, :rel, 'SELECT')"),
                    {"rel": qualified},
                ).scalar()
        except SQLAlchemyError:
            can = False
        if can:
            accessible.append(table_name)
        else:
            inaccessible.append((table_name, "SELECT privilege missing"))
    return accessible, inaccessible


def _check_postgres_stats(conn: Connection) -> dict[str, bool]:
    stats: dict[str, bool] = {}
    for key, relation in [
        ("pg_class", "pg_catalog.pg_class"),
        ("pg_stats", "pg_catalog.pg_stats"),
    ]:
        try:
            with conn.begin_nested():
                value = conn.execute(
                    text("SELECT has_table_privilege(current_user, :rel, 'SELECT')"),
                    {"rel": relation},
                ).scalar()
            stats[key] = bool(value)
        except SQLAlchemyError:
            stats[key] = False
    return stats


def _check_mysql_tables(
    conn: Connection,
    schema: str | None,
    table_names: list[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    schema_name = schema or conn.dialect.default_schema_name
    if not schema_name:
        return list(table_names), []
    accessible: list[str] = []
    inaccessible: list[tuple[str, str]] = []
    preparer = conn.dialect.identifier_preparer
    for table_name in table_names:
        qualified = f"{preparer.quote_identifier(schema_name)}.{preparer.quote_identifier(table_name)}"
        ok = _probe_success(conn, f"SELECT 1 FROM {qualified} LIMIT 0")
        if ok:
            accessible.append(table_name)
        else:
            inaccessible.append(
                (table_name, "SELECT privilege missing or table inaccessible")
            )
    return accessible, inaccessible


def _check_mysql_stats(conn: Connection) -> dict[str, bool]:
    return {
        "information_schema.tables": _probe_success(
            conn, "SELECT 1 FROM information_schema.TABLES LIMIT 1"
        ),
        "information_schema.column_statistics": _probe_success(
            conn, "SELECT 1 FROM information_schema.COLUMN_STATISTICS LIMIT 1"
        ),
    }


def _probe_success(conn: Connection, sql: str, params: dict | None = None) -> bool:
    try:
        if conn.dialect.name == "postgresql":
            with conn.begin_nested():
                conn.execute(text(sql), params or {}).close()
        else:
            conn.execute(text(sql), params or {}).close()
        return True
    except SQLAlchemyError:
        return False


def _check_table_exists(conn: Connection, table_name: str) -> bool:
    try:
        row = conn.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1"
            ),
            {"name": table_name},
        ).first()
        return row is not None
    except SQLAlchemyError:
        return False


def format_warnings(report: PermissionReport) -> list[str]:
    """Return human-readable warning strings for missing privileges."""
    warnings: list[str] = []

    if report.inaccessible_tables:
        names = ", ".join(name for name, _ in report.inaccessible_tables)
        count = len(report.inaccessible_tables)
        warnings.append(f"SELECT denied on {count} table(s): {names}.")
        hint = _grant_hint(report.dialect, report.schema)
        if hint:
            warnings.append(f"  Fix: {hint}")
        if report.accessible_tables:
            warnings.append(
                f"  Skipping {count} table(s); continuing with {len(report.accessible_tables)}."
            )

    missing = {key: ok for key, ok in report.stats_access.items() if not ok}
    if missing:
        names = ", ".join(sorted(missing))
        warnings.append(f"Catalog stats unreadable: {names}.")
        warnings.append(
            "  Row-count estimates may fall back to exact COUNT(*); column histograms will be skipped."
        )
        if report.dialect == "sqlite":
            warnings.append(
                "  Fix: run ANALYZE on the database to populate sqlite_stat1."
            )

    return warnings


def _grant_hint(dialect: str, schema: str | None) -> str:
    schema_name = schema or "<schema>"
    if dialect == "postgresql":
        return f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema_name} TO <role>;"
    if dialect in {"mysql", "mariadb"}:
        return f"GRANT SELECT ON `{schema_name}`.* TO '<user>'@'<host>';"
    return ""
