"""전용 PostgreSQL 테스트 DB에서 Incident와 Outbox 경계를 검증합니다."""

import os
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.errors import CheckViolation
from psycopg.types.json import Jsonb

from src.application.ports.repositories import IncidentConflict
from src.domain.incidents.enums import IncidentStatus, Priority, Severity
from src.domain.incidents.models import Evidence, Incident, StateTransition
from src.domain.incidents.transitions import transition
from src.infrastructure.jobs.outbox_worker import OutboxWorker, RetryableProcessingError
from src.infrastructure.migrations import migrate
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture(identifier: str, store: str) -> Incident:
    return Incident(
        id=identifier,
        display_id=f"SMOKE-{identifier[-8:].upper()}",
        title="PostgreSQL 통합 검증용 인시던트",
        severity=Severity.HIGH,
        status=IncidentStatus.DETECTED,
        store=store,
        owner="통합 검증",
        created_at="2026-10-02T09:00:00Z",
        sla_due_at="2026-10-03T09:00:00Z",
        timeline=[StateTransition(IncidentStatus.DETECTED, "2026-10-02T09:00:00Z")],
        evidence=[
            Evidence(
                "smoke-evidence",
                "temperature_sensor",
                "telemetry",
                "냉장 온도 기록",
                0.95,
            )
        ],
        priority=Priority.P1,
    )


def count_events(connection: psycopg.Connection, incident_id: str) -> int:
    row = connection.execute(
        "SELECT count(*) FROM serviq_outbox WHERE incident_id=%s",
        (incident_id,),
    ).fetchone()
    check(row is not None, "Outbox 건수를 조회하지 못했습니다.")
    return row[0]


def verify_repository(
    dsn: str,
    connection: psycopg.Connection,
    identifier: str,
    store: str,
) -> tuple[Incident, list[str]]:
    repository = PostgresIncidentRepository(dsn)
    original = fixture(identifier, store)
    created = repository.save(original)
    check(created.version == 1, "새 Incident는 버전 1이어야 합니다.")
    check(
        repository.get(identifier) == created,
        "저장한 Domain 객체가 동일하게 복원되어야 합니다.",
    )
    check(
        repository.get(f"missing-{identifier}") is None,
        "없는 Incident는 None을 반환해야 합니다.",
    )
    check(
        repository.list(
            status=IncidentStatus.DETECTED, severity=Severity.HIGH, store=store
        )
        == [created],
        "상태·심각도·매장 결합 필터가 일치하지 않습니다.",
    )
    check(
        repository.list(status=IncidentStatus.TRIAGED, store=store) == [],
        "일치하지 않는 상태 필터가 데이터를 반환했습니다.",
    )
    check(
        repository.list(severity=Severity.LOW, store=store) == [],
        "일치하지 않는 심각도 필터가 데이터를 반환했습니다.",
    )
    check(
        count_events(connection, identifier) == 1,
        "생성 이벤트가 한 건 기록되어야 합니다.",
    )

    classified = repository.save(
        transition(created, IncidentStatus.TRIAGED, "2026-10-02T09:01:00Z")
    )
    check(classified.version == 2, "상태 변경 후 버전이 증가해야 합니다.")
    check(
        repository.get(identifier) == classified,
        "상태와 타임라인이 함께 저장되어야 합니다.",
    )
    check(
        count_events(connection, identifier) == 2,
        "상태 변경 이벤트가 함께 기록되어야 합니다.",
    )
    for stale in (replace(created, owner="오래된 변경"), original):
        try:
            repository.save(stale)
        except IncidentConflict:
            pass
        else:
            raise AssertionError("오래된 버전 또는 중복 생성은 충돌해야 합니다.")
    check(
        repository.get(identifier) == classified,
        "실패한 저장이 Incident를 변경했습니다.",
    )
    check(
        count_events(connection, identifier) == 2,
        "충돌한 저장이 이벤트를 추가했습니다.",
    )
    edited = repository.save(replace(classified, owner="담당자 변경"))
    check(edited.version == 3, "내용 변경도 새 버전으로 저장되어야 합니다.")
    check(
        count_events(connection, identifier) == 2,
        "상태가 같은 변경은 상태 이벤트를 추가하지 않아야 합니다.",
    )
    rows = connection.execute(
        "SELECT event_id,payload FROM serviq_outbox WHERE incident_id=%s ORDER BY created_at,event_id",
        (identifier,),
    ).fetchall()
    check(
        {value[1]["event_type"] for value in rows}
        == {"incident.created", "incident.state_changed"},
        "생성과 전이 이벤트 계약이 일치하지 않습니다.",
    )
    check(
        {value[1]["aggregate_version"] for value in rows} == {1, 2},
        "이벤트 버전이 저장 버전과 일치하지 않습니다.",
    )
    print("[통과] Repository 생성·조회·필터·버전 충돌·상태 이벤트")
    return edited, [str(value[0]) for value in rows]


def verify_atomicity(
    dsn: str,
    connection: psycopg.Connection,
    identifier: str,
    store: str,
    constraint_name: str,
) -> None:
    # 이 UUID 전용 이벤트만 거부하여 실제 DB 오류 뒤 전체 트랜잭션 롤백을 확인합니다.
    connection.execute(
        sql.SQL(
            "ALTER TABLE serviq_outbox ADD CONSTRAINT {} CHECK (incident_id <> {})"
        ).format(sql.Identifier(constraint_name), sql.Literal(identifier))
    )
    repository = PostgresIncidentRepository(dsn)
    try:
        repository.save(fixture(identifier, store))
    except CheckViolation:
        pass
    else:
        raise AssertionError("Outbox INSERT 실패가 저장을 실패시켜야 합니다.")
    check(
        repository.get(identifier) is None, "Outbox 실패 뒤 Incident가 남아 있습니다."
    )
    check(
        count_events(connection, identifier) == 0,
        "롤백한 Outbox 이벤트가 남아 있습니다.",
    )
    print("[통과] Outbox INSERT 실패 시 Incident와 이벤트 원자적 롤백")


def verify_worker(dsn: str, connection: psycopg.Connection, event_ids: list[str]) -> None:
    now = connection.execute("SELECT CURRENT_TIMESTAMP").fetchone()[0]
    worker = OutboxWorker(connection, clock=lambda: now)

    # 다른 연결이 보유한 첫 이벤트 잠금을 건너뛰어 두 번째 이벤트를 인수합니다.
    with psycopg.connect(dsn, autocommit=True) as blocker, blocker.transaction():
        blocker.execute(
            "SELECT event_id FROM serviq_outbox WHERE event_id=%s FOR UPDATE",
            (event_ids[0],),
        ).fetchone()
        claimed = worker.claim()
        check(
            claimed is not None and claimed.event_id == event_ids[1],
            "Worker는 잠긴 이벤트를 건너뛰어야 합니다.",
        )
        check(worker.complete(claimed), "인수한 이벤트를 완료하지 못했습니다.")
    check(worker.run_once(), "남은 이벤트를 한 번 처리해야 합니다.")
    completed = connection.execute(
        "SELECT count(*) FROM serviq_outbox WHERE event_id=ANY(%s::uuid[]) AND status='COMPLETED'",
        (event_ids,),
    ).fetchone()[0]
    check(completed == 2, "두 이벤트가 완료 상태여야 합니다.")

    connection.execute(
        "UPDATE serviq_outbox SET status='RUNNING',attempts=1,lease_until=%s,processed_at=NULL WHERE event_id=%s",
        (now - timedelta(seconds=1), event_ids[0]),
    )
    reclaimed = worker.claim()
    check(
        reclaimed is not None
        and reclaimed.event_id == event_ids[0]
        and reclaimed.attempts == 2,
        "만료한 잠금을 새 시도로 인수해야 합니다.",
    )
    check(
        not worker.complete(replace(reclaimed, attempts=1)),
        "이전 시도의 완료 기록이 새 작업을 덮어쓸 수 없습니다.",
    )
    check(worker.complete(reclaimed), "새 시도는 완료할 수 있어야 합니다.")

    connection.execute(
        "UPDATE serviq_outbox SET status='PENDING',attempts=0,max_attempts=3,available_at=%s,lease_until=NULL,processed_at=NULL WHERE event_id=%s",
        (now, event_ids[1]),
    )

    def temporary_failure(_event) -> None:
        raise RetryableProcessingError("일시적인 검증용 실패")

    retry_worker = OutboxWorker(connection, temporary_failure, clock=lambda: now)
    check(retry_worker.run_once(), "일시적 실패 작업을 인수해야 합니다.")
    pending = connection.execute(
        "SELECT status,attempts,available_at FROM serviq_outbox WHERE event_id=%s",
        (event_ids[1],),
    ).fetchone()
    check(
        pending == ("PENDING", 1, now + timedelta(seconds=5)),
        "첫 실패는 5초 후 재시도되어야 합니다.",
    )
    check(not retry_worker.run_once(), "재시도 대기 시각 이전에 작업을 인수했습니다.")
    now += timedelta(seconds=5)
    check(retry_worker.run_once(), "두 번째 시도를 인수해야 합니다.")
    next_time = connection.execute(
        "SELECT available_at FROM serviq_outbox WHERE event_id=%s", (event_ids[1],)
    ).fetchone()[0]
    check(
        next_time == now + timedelta(seconds=10),
        "두 번째 실패는 10초 후 재시도되어야 합니다.",
    )
    now = next_time
    check(retry_worker.run_once(), "마지막 시도를 인수해야 합니다.")
    failed = connection.execute(
        "SELECT status,attempts FROM serviq_outbox WHERE event_id=%s", (event_ids[1],)
    ).fetchone()
    check(failed == ("DLQ", 3), "최대 시도 횟수에서 실패 보관함으로 이동해야 합니다.")

    invalid_payload = connection.execute(
        "SELECT payload FROM serviq_outbox WHERE event_id=%s", (event_ids[0],)
    ).fetchone()[0]
    invalid_payload["event_version"] = 99
    connection.execute(
        "UPDATE serviq_outbox SET status='PENDING',attempts=0,available_at=%s,lease_until=NULL,processed_at=NULL,payload=%s WHERE event_id=%s",
        (now, Jsonb(invalid_payload), event_ids[0]),
    )
    check(worker.run_once(), "잘못된 계약의 이벤트를 인수해야 합니다.")
    invalid = connection.execute(
        "SELECT status,attempts FROM serviq_outbox WHERE event_id=%s", (event_ids[0],)
    ).fetchone()
    check(
        invalid == ("DLQ", 1),
        "계약 오류는 재시도 없이 실패 보관함으로 이동해야 합니다.",
    )
    print("[통과] Worker SKIP LOCKED·단일 처리·잠금 복구·이전 ACK 차단·재시도·DLQ")


def main() -> None:
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("전용 테스트 DB의 SERVIQ_TEST_DATABASE_URL을 설정해 주세요.")
    suffix = uuid4().hex
    identifiers = [f"smoke-{suffix}-incident", f"smoke-{suffix}-rollback"]
    store = f"통합검증-{suffix}"
    constraint_name = f"smoke_outbox_{suffix}"
    migrate(dsn)
    migrate(dsn)
    print("[통과] PostgreSQL 저장소 초기화 반복 실행")
    with psycopg.connect(dsn, autocommit=True) as connection:
        pending = connection.execute(
            "SELECT count(*) FROM serviq_outbox WHERE status IN ('PENDING','RUNNING')"
        ).fetchone()[0]
        check(pending == 0, "다른 대기 작업이 없는 전용 테스트 DB를 사용해 주세요.")
        try:
            _, event_ids = verify_repository(dsn, connection, identifiers[0], store)
            verify_worker(dsn, connection, event_ids)
            verify_atomicity(dsn, connection, identifiers[1], store, constraint_name)
        finally:
            connection.execute(
                sql.SQL(
                    "ALTER TABLE serviq_outbox DROP CONSTRAINT IF EXISTS {}"
                ).format(sql.Identifier(constraint_name))
            )
            with connection.transaction():
                connection.execute(
                    "DELETE FROM serviq_outbox WHERE incident_id=ANY(%s::text[])",
                    (identifiers,),
                )
                connection.execute(
                    "DELETE FROM serviq_incidents WHERE id=ANY(%s::text[])",
                    (identifiers,),
                )
            remaining = connection.execute(
                "SELECT count(*) FROM serviq_incidents WHERE id=ANY(%s::text[])",
                (identifiers,),
            ).fetchone()[0]
            check(remaining == 0, "통합 검증용 Incident 정리에 실패했습니다.")
    print("[통과] UUID 전용 검증 데이터와 임시 제약 정리")


if __name__ == "__main__":
    main()
