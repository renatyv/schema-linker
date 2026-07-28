# Schema Linker
**Agent skill: [`skills/SKILL.md`](skills/SKILL.md)**

**Spec: [`spec/schema_linking.md`](spec/schema_linking.md)**

Schema Linker discovers how tables relate in an existing database and emits a compact, LLM-ready Markdown report of declared PK/FK joins plus inferred join candidates with evidence labels. Useful for text-to-SQL, multi-table query authoring, and join-path debugging. Supports SQLite, PostgreSQL, MySQL, MariaDB, and DuckDB. Requires Python >= 3.10.

It produces a schema-link report (`<database>/<schema>_schema_links.md`): declared PK/FK relationships and inferred join candidates.

AI agents and text-to-SQL pipelines can read this context instead of guessing join paths.

## Quick Start

Install with pip:
```bash
pip install schema-linker
```

Or run instantly with `uvx` (no install needed):
```bash
uvx schema-linker --db-type mysql --user user --password password --database db --schema sch --port 3306
```

This creates a report at `db/sch_schema_links.md`.

The schema-link report lists declared PK/FK joins and inferred join candidates with evidence labels. See [What The Output Contains](#what-the-output-contains) for details.

## What The Output Contains

The schema links `.md` file contains:

- Declared primary-key and foreign-key links from database constraints.
- Inferred links from name, type, cardinality, and containment evidence.
- Evidence labels for each inferred join candidate.

Treat inferred links as candidates, not guaranteed joins. Validate them against the user question and the table data before writing final SQL.

## Database Examples

### SQLite
```bash
schema-linker --db-type sqlite --database path/to/app.sqlite
```

### PostgreSQL
```bash
schema-linker --db-type postgres --database app_db --schema sch --user readonly_user --host localhost --port 5432 --ask-password
```

### MySQL
```bash
schema-linker --db-type mysql --database app_db --user readonly_user --host localhost --port 3306 --ask-password
```

### MariaDB
```bash
schema-linker --db-type mariadb --database app_db --user readonly_user --host localhost --port 3306 --ask-password
```

### DuckDB
```bash
schema-linker --db-type duckdb --database warehouse.duckdb --schema sch
```

## Environment Variables

Connection values can come from environment variables instead of flags:

```bash
SCHEMA_LINKER_DB_TYPE=sqlite \
SCHEMA_LINKER_DATABASE=path/to/app.sqlite \
schema-linker
```

Supported variables:

- `SCHEMA_LINKER_DB_TYPE`
- `SCHEMA_LINKER_DATABASE`
- `SCHEMA_LINKER_DB_HOST`
- `SCHEMA_LINKER_DB_PORT`
- `SCHEMA_LINKER_DB_USER`
- `SCHEMA_LINKER_DB_PASSWORD`
- `SCHEMA_LINKER_SCHEMA`

For server databases, `--host` defaults to `localhost`, `--port` defaults to the database default, and Schema Linker securely prompts for a password when `SCHEMA_LINKER_DB_PASSWORD` is not set.

## Help

```bash
schema-linker -h
```

Table filters:

```bash
schema-linker --db-type sqlite --database app.sqlite --include-tables users,orders,line_items
schema-linker --db-type sqlite --database app.sqlite --exclude-tables audit_log,temp_imports
```

Schema filter:

```bash
schema-linker --db-type postgres --database app_db --schema reporting --user readonly_user --port 5432 --ask-password
```

Options:

- `--include-tables table_a,table_b`: only inspect selected tables.
- `--exclude-tables table_c`: skip selected tables.
- `--include-technical-tables`: link migration/framework tables that are skipped by default.
- `--containment-threshold 0.8`: minimum exact containment for inferred links.
- `--max-distinct-values 10000`: maximum distinct values loaded per candidate column.

## Python API

Use the lower-level API when you already have a SQLAlchemy engine or need options:

```python
from sqlalchemy import create_engine
from schema_linker import SchemaLinkOptions, link_schema

engine = create_engine("sqlite:///path/to/app.sqlite")

schema_links_md = link_schema(
    engine,
    SchemaLinkOptions(containment_threshold=0.9),
)
```

## License

The Schema Linker source code is licensed under the MIT License. See `LICENCE`.

Third-party Python dependencies remain under their own upstream licenses. See `THIRD_PARTY_NOTICES.md` for a dependency license summary.
