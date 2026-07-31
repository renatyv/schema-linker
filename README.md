# Schema Linker

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)

**Agent skill: [`skills/SKILL.md`](skills/SKILL.md)**

**Spec: [`spec/schema_linking.md`](spec/schema_linking.md)**

Schema Linker discovers how tables relate in an existing database and emits a compact, LLM-ready Markdown report of declared PK/FK joins plus inferred join candidates with evidence labels. Useful for text-to-SQL, multi-table query authoring, and join-path debugging. Supports SQLite, PostgreSQL, MySQL, MariaDB, and DuckDB. Requires Python >= 3.10.

It writes one Markdown report per schema at `<db_name>/<schema>_schema_links.md` (for example `app/main_schema_links.md`), where `<db_name>` is the database or file name without its directory or extension. Use `--output` to change the directory.

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

The output directory defaults to the database name (`<db_name>/`). For SQLite/DuckDB the schema is `main`, so `--database path/to/app.sqlite` writes `app/main_schema_links.md`. Override the directory with `--output`. See [What The Output Contains](#what-the-output-contains) for what's inside.

## What The Output Contains

The schema links `.md` file contains:

- Declared primary-key and foreign-key links from database constraints. Omitted by default to save tokens; include them with `--show-declared-links`.
- Inferred links from name, type, cardinality, and containment evidence.
- Evidence labels for each inferred join candidate. Omitted by default to save tokens; include them with `--show-evidence`.

Treat inferred links as candidates, not guaranteed joins. Validate them against the user question and the table data before writing final SQL.

## How It Works

Declared links are read straight from the database's primary/foreign-key constraints. For everything not already covered by an FK, Schema Linker runs a cheap-to-expensive pipeline (full details in [`spec/schema_linking.md`](spec/schema_linking.md)):

1. **Metadata** — skip FK-covered columns and pairs with mismatched data types.
2. **Cardinality** — estimate `COUNT(DISTINCT col)`; drop near-unique free text, keep moderate, ID-like columns.
3. **Name/type** — match column names (Levenshtein-style similarity) to find strong candidates worth a spot-check.
4. **Containment** — extract distinct values only for the survivors, then use MinHash + LSH Ensemble to find one-way set containment (this handles unequal cardinalities, unlike Jaccard).
5. **Verify** — confirm each candidate with an exact containment check and require at least three independent pieces of evidence.

A link survives only when name, type, cardinality, and containment agree — which is why evidence is reported per signal.

## Sample Output

This is the real report produced by the [runnable example](#runnable-example) below (a tiny SQLite shop database). By default the Declared PK/FK Links section is omitted to save tokens:

````markdown
# Schema Links

- version: 0.0.1
- dialect: sqlite
- database: examples/shop.sqlite
- schema: main

## Inferred Links

### customers.customer_id
- inferred: support_tickets.customer_id
- declared: orders.customer_id
````

Add `--show-declared-links` to prepend the declared section at the top:

````markdown
## Declared PK/FK Links

order_lines.order_id -> orders.order_id
orders.customer_id -> customers.customer_id
````

- **Declared PK/FK Links** come straight from database constraints — the safe, guaranteed joins. Declared links are always used to group the inferred links below; the section itself is optional.
- **Inferred Links** are grouped by shared value domain. Under each anchor, `inferred:` lists new join candidates and `declared:` lists columns already covered by a foreign key (shown for context).

Here `support_tickets.customer_id` is flagged as a likely join onto `customers.customer_id` even though there is no FK constraint — exactly the case text-to-SQL agents usually have to guess.

Add `--show-evidence` to see the signal behind each candidate (real output from the same database):

````markdown
### customers.customer_id
- inferred:
  - support_tickets.customer_id: minhash containment candidate, moderate ID-like cardinality, name match, shared name tokens, similar names, type match
- declared: orders.customer_id
````

Evidence labels report the *why* (`name match`, `table-name id match`, `shared name tokens`, `similar names`, `type match`, `minhash containment candidate`) and the *confidence* (`same distinct count`, `similar distinct counts`, `low cardinality`, `moderate cardinality`, `moderate ID-like cardinality`).

## Runnable Example

Reproduce the output above against a seedable SQLite database in [`examples/`](examples):

```bash
# 1. build examples/shop.sqlite (customers, orders, order_lines, support_tickets)
python examples/seed_shop.py

# 2. link it; --output examples writes examples/main_schema_links.md
schema-linker --db-type sqlite --database examples/shop.sqlite --output examples

cat examples/main_schema_links.md
```

The fixture deliberately leaves `support_tickets.customer_id` without a foreign key, so inference — not the catalog — surfaces that join. Re-run with `schema-linker ... --show-evidence` to see the evidence labels above.

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
- `--show-evidence`: include evidence labels on inferred links (off by default to save tokens).
- `--show-declared-links`: include the Declared PK/FK Links section (off by default to save tokens; declared links are still used to group inferred links).

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
