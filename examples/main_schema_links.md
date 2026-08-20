# Schema Links

- version: 0.0.2
- dialect: sqlite
- database: examples/shop.sqlite
- schema: main

## Declared PK/FK Links

order_lines.order_id -> orders.order_id
orders.customer_id -> customers.customer_id

## Inferred Links

### customers.customer_id
- inferred: support_tickets.customer_id
- declared: orders.customer_id
