"""Build a tiny SQLite database for the Schema Linker runnable example.

Run from the repo root:

    python examples/seed_shop.py

Creates ``examples/shop.sqlite`` with four tables that mirror a small
e-commerce schema. Three relationships are declared as foreign keys; the
fourth (``support_tickets.customer_id``) is intentionally left undeclared so
Schema Linker has to infer it.

Schema:

    customers.customer_id (PK)
    orders.customer_id        -> customers.customer_id   (declared FK)
    order_lines.order_id      -> orders.order_id         (declared FK)
    support_tickets.customer_id -> customers.customer_id (NO FK, should be inferred)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "shop.sqlite"


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            name        TEXT NOT NULL
        );

        CREATE TABLE orders (
            order_id    INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL
                        REFERENCES customers(customer_id)
        );

        CREATE TABLE order_lines (
            line_id   INTEGER PRIMARY KEY,
            order_id  INTEGER NOT NULL
                      REFERENCES orders(order_id),
            product   TEXT NOT NULL,
            quantity  INTEGER NOT NULL
        );

        CREATE TABLE support_tickets (
            ticket_id   INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            subject     TEXT NOT NULL
        );
        """
    )

    customers = [(i, f"Customer {i}") for i in range(1, 21)]
    # orders: 40 orders spread across the 20 customers
    orders = [(i, ((i - 1) % 20) + 1) for i in range(1, 41)]
    # order_lines: 3 lines per order
    order_lines = [
        (i, ((i - 1) // 3) + 1, f"Product {((i - 1) % 5) + 1}", ((i - 1) % 5) + 1)
        for i in range(1, 121)
    ]
    # support_tickets: a subset of customers (1..15) so the values are contained
    # in customers.customer_id, which lets inference surface the hidden join.
    tickets = [(i, ((i - 1) % 15) + 1, f"Ticket {i}") for i in range(1, 16)]

    conn.executemany("INSERT INTO customers VALUES (?, ?)", customers)
    conn.executemany("INSERT INTO orders VALUES (?, ?)", orders)
    conn.executemany("INSERT INTO order_lines VALUES (?, ?, ?, ?)", order_lines)
    conn.executemany("INSERT INTO support_tickets VALUES (?, ?, ?)", tickets)

    conn.commit()
    conn.close()
    print(f"Built {DB_PATH}")


if __name__ == "__main__":
    main()
