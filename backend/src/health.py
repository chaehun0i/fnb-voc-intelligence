"""컨테이너에서 실제 DB 연결과 최소 조회를 확인합니다."""

from psycopg import Error as DatabaseError

from src.data.database import check_health, connect


def main() -> int:
    try:
        from src.config import settings
    except ValueError:
        return 1

    if settings.postgresql_url is None:
        return 1
    try:
        connection = connect(settings.postgresql_url)
    except (DatabaseError, OSError):
        return 1
    ready = False
    try:
        ready = check_health(connection)
    except (DatabaseError, OSError):
        ready = False
    finally:
        try:
            connection.close()
        except (DatabaseError, OSError):
            ready = False
    return int(not ready)


if __name__ == "__main__":
    raise SystemExit(main())
