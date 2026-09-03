# Day 4 PostgreSQL Schema

## Local setup

Set `POSTGRESQL_URL` in `.env` to a PostgreSQL database URL. The project keeps connection concerns in `src/data/database.py`; domain models remain independent from database access.

## Relationships

- `products` is the parent of `reviews`.
- Versioned `taxonomy_categories` is the parent of `taxonomy_keywords`.
- `review_classifications` links a review to one or more versioned taxonomy categories, preserving score and JSON evidence.

## Initialization

`initialize_schema(connection)` creates tables in FK-safe order and uses `CREATE TABLE IF NOT EXISTS`, so it is idempotent. It never seeds business data.

## Repositories

Product/review and taxonomy/classification repository helpers live in `src/data/repositories.py`. Use them behind the connection boundary for local persistence work.

## Validation

```bash
ruff check .
pytest
```

Vector Search is intentionally out of scope for Day 4.
