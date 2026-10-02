"""기존 Product/Review 테이블과 분리된 ServIQ 저장소를 초기화합니다."""

import os
from importlib.resources import files

import psycopg


def migration_sql() -> str:
    """실행 위치와 관계없이 설치된 SQL 리소스를 읽습니다."""
    return files("db.migrations").joinpath("001_serviq.sql").read_text(encoding="utf-8")


def migrate(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(migration_sql())


def main() -> None:
    dsn = os.environ.get("SERVIQ_DATABASE_URL")
    if not dsn:
        raise SystemExit("SERVIQ_DATABASE_URL을 설정해 주세요.")
    migrate(dsn)
    print("ServIQ 저장소 초기화를 완료했습니다.")


if __name__ == "__main__":
    main()
