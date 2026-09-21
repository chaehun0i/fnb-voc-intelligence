"""Idempotent PostgreSQL schema initialization entry point."""

from src.config import settings
from src.data.database import connect, initialize_schema


def main() -> int:
    if settings.postgresql_url is None:
        raise ValueError("POSTGRESQL_URL is required")
    connection = connect(settings.postgresql_url)
    try:
        initialize_schema(connection)
        connection.commit()
    finally:
        connection.close()
    return 0
