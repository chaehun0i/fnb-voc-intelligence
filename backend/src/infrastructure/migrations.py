"""기존 Product/Review 테이블과 분리된 ServIQ 저장소를 초기화합니다."""

import hashlib
import os
from importlib.resources import files

import psycopg


def migration_sql() -> str:
    """실행 위치와 관계없이 설치된 SQL 리소스를 읽습니다."""
    root = files("db.migrations")
    return "\n".join(item.read_text(encoding="utf-8") for item in
                     sorted(root.iterdir(), key=lambda item: item.name)
                     if item.name.endswith(".sql"))


def migrate(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        # 역사적 CHECK 상한을 재적용하면 새로운 단계 이력이 있는 DB의 재시작이 실패합니다.
        # 전체 변경은 한 트랜잭션이며 동시 초기화도 직렬화합니다.
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('serviq-migrations',0))")
        connection.execute("""CREATE TABLE IF NOT EXISTS serviq_schema_migrations (
            name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())""")
        legacy = connection.execute("SELECT to_regclass('serviq_rca_effects') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM serviq_schema_migrations)").fetchone()[0]
        for item in sorted(files("db.migrations").iterdir(), key=lambda item: item.name):
            if not item.name.endswith(".sql"):
                continue
            sql = item.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            previous = connection.execute("SELECT checksum FROM serviq_schema_migrations WHERE name=%s", (item.name,)).fetchone()
            if previous:
                if previous[0] != checksum:
                    raise ValueError("이미 적용한 migration 원문은 변경할 수 없습니다.")
                continue
            # Day 24까지의 기존 runner는 001..014를 원자적으로 실행했습니다.
            # 마지막 원본 테이블이 존재하는 legacy DB만 그 기준선을 채택합니다.
            if not (legacy and int(item.name.split('_')[0]) <= 14):
                connection.execute(sql)
            connection.execute("INSERT INTO serviq_schema_migrations(name,checksum) VALUES(%s,%s)", (item.name, checksum))


def main() -> None:
    dsn = os.environ.get("SERVIQ_DATABASE_URL")
    if not dsn:
        raise SystemExit("SERVIQ_DATABASE_URL을 설정해 주세요.")
    migrate(dsn)
    print("ServIQ 저장소 초기화를 완료했습니다.")


if __name__ == "__main__":
    main()
