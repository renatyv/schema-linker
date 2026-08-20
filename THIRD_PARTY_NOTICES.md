# Third-Party Notices

Schema Linker source code is licensed under the MIT License. This notice summarizes licenses for declared Python dependencies.

This file is informational and is not legal advice. Check each upstream project for the authoritative license text.

## Runtime Dependencies

| Package | Used by | License |
| --- | --- | --- |
| `datasketch` | Required | MIT |
| `numpy` | Transitive dependency of `datasketch` | BSD-3-Clause |
| `scipy` | Transitive dependency of `datasketch` | BSD-3-Clause, with bundled binary notices for some wheels |
| `sqlalchemy` | Required | MIT |
| `greenlet` | Transitive dependency of `sqlalchemy` on supported platforms | MIT |
| `typing-extensions` | Transitive dependency of `sqlalchemy` on some Python versions | PSF-2.0 |
| `psycopg` | Required (PostgreSQL driver) | LGPL-3.0-only or later, as published by upstream metadata |
| `psycopg-binary` | Transitive dependency of `psycopg` | LGPL-3.0-only or later, as published by upstream metadata |
| `tzdata` | Transitive dependency of `psycopg` on some platforms | Apache-2.0 |
| `pymysql` | Required (MySQL/MariaDB driver) | MIT |
| `duckdb-engine` | Required (DuckDB driver) | MIT |
| `duckdb` | Transitive dependency of `duckdb-engine` | MIT |
| `packaging` | Transitive dependency of `duckdb-engine` | Apache-2.0 or BSD-2-Clause |
| `rich` | Required (progress bars) | MIT |
| `markdown-it-py` | Transitive dependency of `rich` | MIT |
| `mdurl` | Transitive dependency of `markdown-it-py` | MIT |
| `pygments` | Transitive dependency of `rich` | BSD-2-Clause |

The PostgreSQL, MySQL/MariaDB, and DuckDB drivers are installed by default and are only used when connecting to their respective databases. The LGPL-licensed `psycopg` driver is a runtime dependency; SQLite needs no external driver.

## Development And Build Dependencies

| Package | Used by | License |
| --- | --- | --- |
| `hatchling` | Build backend | MIT |
