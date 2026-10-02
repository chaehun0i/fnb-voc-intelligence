"""Container readiness probe without web-server dependencies."""

from src.data.database import check_health, connect


def main() -> int:
    from src.config import settings

    if settings.postgresql_url is None:
        return 1
    connection = connect(settings.postgresql_url)
    try:
        return int(not check_health(connection))
    finally:
        connection.close()
