from __future__ import annotations

import re
from pathlib import Path

SENSITIVE_NAME_PARTS = ("password", "passwd", "pwd", "hash", "salt", "secret", "token")

# Migration-framework and DB-internal tables with no analytical value. Excluded
# from profiling/linking by default; case-insensitive match on the table name.
TECHNICAL_TABLES = frozenset(
    {
        # Rails / Active Record
        "schema_migrations",
        "ar_internal_metadata",
        # Django
        "django_migrations",
        "django_session",
        "django_content_type",
        "django_admin_log",
        # Laravel
        "migrations",
        # Java
        "flyway_schema_history",
        "databasechangelog",
        "databasechangeloglock",
        # .NET EF Core
        "__efmigrationshistory",
        # Python
        "alembic_version",
        # Node
        "sequelize_meta",
        "knex_migrations",
        "knex_migrations_lock",
        "_prisma_migrations",
        # SQLite internal
        "sqlite_sequence",
    }
)


def is_sensitive(column_name: str) -> bool:
    lower_name = column_name.lower()
    return any(part in lower_name for part in SENSITIVE_NAME_PARTS)


def is_technical_table(table_name: str) -> bool:
    return table_name.lower() in TECHNICAL_TABLES


def parse_table_set(value: str | None) -> frozenset[str] | None:
    if not value:
        return None
    return frozenset(table.strip() for table in value.split(",") if table.strip())


def default_output_path(database: str) -> Path:
    name = Path(database).name
    db_name = Path(name).stem or name
    return Path(db_name)


def output_component(value: str) -> str:
    """Map database object names to a single safe output path component."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip(".") or "unnamed"
