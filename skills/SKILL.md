---
name: schema-linker
description: Use when an AI agent needs to discover join paths and schema links (declared PK/FK relationships plus inferred join candidates with evidence) for SQL join planning, text-to-SQL, multi-table query authoring, or query debugging with schema-linker.
compatibility: opencode, OpenWork, PI, Claude, ChatGPT, custom agent runners
---

# Schema Linker

Use this skill to discover how tables relate before writing joins. It runs `schema-linker` to produce a Markdown report of declared PK/FK relationships and inferred join candidates with evidence labels.

## When To Use

- Use when the user asks for join paths, relationships between tables, foreign-key discovery, or schema links.
- Use before writing multi-table SQL when the join paths are not obvious.
- Use when debugging a query that returns wrong/empty rows because of a guessed join.
- Do not treat inferred links as guaranteed joins; validate them against the user question and the data.
- Do not perform destructive database operations.

## Connection And Options

schema-linker supports SQLite, PostgreSQL, MySQL, MariaDB, and DuckDB (all drivers ship with the base install; no extra is needed).

Run the linker with `uvx` (no install needed). PostgreSQL example:

```bash
uvx schema-linker --db-type postgres --database app_db --user readonly_user --host localhost --port 5432 --ask-password
```

See every flag and its default — connection details, `--schema`, `--include-tables`/`--exclude-tables`, `--containment-threshold`, `--max-distinct-values`, `--output`, and the `SCHEMA_LINKER_*` environment-variable fallbacks — with:

```bash
uvx schema-linker -h
```

For frequent use, install once with `uv tool install schema-linker` and run `schema-linker ...` directly.

## Using Inferred Links

- Prefer declared PK/FK links over inferred links.
- Use an inferred link only when its evidence fits the user question.
- Increase `--containment-threshold` to reduce noisy inferred links.
- Lower `--max-distinct-values` to cap memory and database load.
- Inferred links with fewer than three pieces of evidence are omitted by default.

## Safety And Performance

- Prefer a read-only database user.
- Run against production during low-load windows.
- Use `--include-tables` to narrow large databases.
- Review generated files before sending them to external services.
