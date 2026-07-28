from __future__ import annotations

import argparse
import getpass
import os
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.engine import URL

DRIVER_NAMES = {
    "sqlite": "sqlite",
    "postgres": "postgresql+psycopg",
    "mysql": "mysql+pymysql",
    "mariadb": "mysql+pymysql",
    "duckdb": "duckdb",
}

DEFAULT_PORTS = {
    "postgres": 5432,
    "mysql": 3306,
    "mariadb": 3306,
}

def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db-type",
        choices=sorted(DRIVER_NAMES),
        default=None,
        help="Database type. Defaults to SCHEMA_LINKER_DB_TYPE.",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Database name, or file path for SQLite/DuckDB. Defaults to SCHEMA_LINKER_DATABASE.",
    )
    parser.add_argument("--host", default=None, help="Database host. Defaults to SCHEMA_LINKER_DB_HOST or localhost.")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Database port. Defaults to SCHEMA_LINKER_DB_PORT or the database server default.",
    )
    parser.add_argument("--user", default=None, help="Database user. Defaults to SCHEMA_LINKER_DB_USER.")
    parser.add_argument(
        "--password",
        default=None,
        help="Database password. Defaults to SCHEMA_LINKER_DB_PASSWORD, then a secure prompt for server databases.",
    )
    parser.add_argument("--ask-password", action="store_true", help="Prompt securely for the database password.")
    parser.add_argument(
        "--schema",
        default=None,
        help="Schema to inspect. Defaults to SCHEMA_LINKER_SCHEMA; without either, all user schemas are inspected.",
    )


def resolve_database_url(args: argparse.Namespace, parser: argparse.ArgumentParser) -> URL:
    db_type = _value(args, "db_type", "SCHEMA_LINKER_DB_TYPE")
    if not db_type:
        parser.error(
            "database connection is required. Use friendly flags like "
            "--db-type sqlite --database path/to.db, or set SCHEMA_LINKER_DB_TYPE and SCHEMA_LINKER_DATABASE."
        )
    if db_type not in DRIVER_NAMES:
        parser.error(f"unsupported --db-type {db_type!r}; choose one of: {', '.join(sorted(DRIVER_NAMES))}")

    database = _value(args, "database", "SCHEMA_LINKER_DATABASE")
    if not database:
        parser.error("--database or SCHEMA_LINKER_DATABASE is required")

    if db_type in {"sqlite", "duckdb"}:
        return URL.create(DRIVER_NAMES[db_type], database=database)

    host = _value(args, "host", "SCHEMA_LINKER_DB_HOST") or "localhost"
    port = _optional_int(_value(args, "port", "SCHEMA_LINKER_DB_PORT"), parser) or DEFAULT_PORTS[db_type]
    user = _value(args, "user", "SCHEMA_LINKER_DB_USER")
    password = _value(args, "password", "SCHEMA_LINKER_DB_PASSWORD")
    if args.ask_password or password is None:
        password = getpass.getpass("Database password: ")
    return URL.create(DRIVER_NAMES[db_type], username=user, password=password, host=host, port=port, database=database)


def resolve_schema(args: argparse.Namespace) -> str | None:
    """Return an explicitly selected schema, if any."""
    return _value(args, "schema", "SCHEMA_LINKER_SCHEMA")


def list_schemas(engine: Engine, selected_schema: str | None = None) -> list[str]:
    """List non-system schemas that contain tables for this database connection."""
    if selected_schema:
        return [selected_schema]

    dialect = engine.dialect.name
    if dialect == "sqlite":
        return ["main"]
    if dialect in {"mysql", "mariadb"}:
        return [engine.dialect.default_schema_name or engine.url.database or "main"]

    system_schemas = {"information_schema", "pg_catalog", "pg_toast"}
    inspector = inspect(engine)
    schemas = [
        schema
        for schema in inspector.get_schema_names()
        if schema not in system_schemas and inspector.get_table_names(schema=schema)
    ]
    return sorted(schemas)


def _value(args: argparse.Namespace, arg_name: str, env_name: str) -> Any:
    value = getattr(args, arg_name)
    if value is not None:
        return value
    return os.environ.get(env_name)


def _optional_int(value: Any, parser: argparse.ArgumentParser) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except ValueError:
        parser.error("SCHEMA_LINKER_DB_PORT must be an integer")
