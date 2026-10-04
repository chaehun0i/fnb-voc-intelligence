"""이벤트를 제한된 횟수로 처리하고 결과를 PostgreSQL에 기록합니다."""

import argparse
import json
import logging
import math
import os
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from src.domain.incidents.enums import IncidentStatus

logger = logging.getLogger(__name__)

EXHAUSTED_LEASE_SQL = """
    UPDATE serviq_outbox SET status='DLQ', lease_until=NULL,
        error_summary='실행 잠금 만료 후 최대 시도 횟수에 도달했습니다.',
        processed_at=%s
    WHERE status='RUNNING' AND lease_until <= %s AND attempts >= max_attempts
"""
CLAIM_SQL = """
    SELECT event_id, incident_id, event_type, payload, attempts, max_attempts
    FROM serviq_outbox
    WHERE attempts < max_attempts AND (
        (status='PENDING' AND available_at <= %s)
        OR (status='RUNNING' AND lease_until <= %s)
    )
    ORDER BY created_at, event_id
    LIMIT 1 FOR UPDATE SKIP LOCKED
"""
START_SQL = """
    UPDATE serviq_outbox SET status='RUNNING', attempts=attempts+1,
        lease_until=%s, processed_at=NULL
    WHERE event_id=%s
"""
COMPLETE_SQL = """
    UPDATE serviq_outbox SET status='COMPLETED', lease_until=NULL,
        processed_at=%s, error_summary=NULL
    WHERE event_id=%s AND status='RUNNING' AND attempts=%s AND lease_until > %s
    RETURNING event_id
"""
FAIL_SQL = """
    UPDATE serviq_outbox SET status=%s, available_at=%s,
        lease_until=NULL, error_summary=%s, processed_at=%s
    WHERE event_id=%s AND status='RUNNING' AND attempts=%s AND lease_until > %s
    RETURNING event_id
"""


@dataclass(frozen=True)
class OutboxEvent:
    event_id: str
    incident_id: str | None
    event_type: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


class RetryableProcessingError(Exception):
    """일시적인 처리 실패에만 사용하며 남은 횟수 안에서 재시도합니다."""


class InvalidOutboxEvent(Exception):
    """지원하지 않는 이벤트나 잘못된 계약은 재시도하지 않습니다."""


def _log(event: OutboxEvent, status: str) -> None:
    logger.info(
        json.dumps(
            {
                "event_id": event.event_id,
                "incident_id": event.incident_id,
                "event_type": event.event_type,
                "attempt": event.attempts,
                "status": status,
            },
            ensure_ascii=False,
        )
    )


def validate_and_log(event: OutboxEvent) -> None:
    """현재 처리기는 계약을 확인하고 로그만 남기며 외부 조치를 수행하지 않습니다."""
    payload = event.payload
    if not isinstance(payload, dict):
        raise InvalidOutboxEvent("이벤트 본문은 객체여야 합니다.")
    if event.event_type == "config.changed":
        try:
            if (event.incident_id is not None or payload["event_type"] != event.event_type
                    or payload["event_id"] != event.event_id or type(payload["event_version"]) is not int
                    or payload["event_version"] != 1 or payload["resource_type"] != "runtime_config"
                    or not isinstance(payload["tenant_id"], str) or not payload["tenant_id"]
                    or payload["aggregate_id"] != payload["tenant_id"] + ":runtime"
                    or type(payload["aggregate_version"]) is not int or payload["aggregate_version"] < 1
                    or not isinstance(payload["correlation_id"], str) or not payload["correlation_id"]
                    or datetime.fromisoformat(payload["occurred_at"]).tzinfo is None):
                raise ValueError("설정 이벤트 참조가 올바르지 않습니다.")
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidOutboxEvent("설정 이벤트 계약을 확인해 주세요.") from error
        _log(event, "validated")
        return
    if (
        event.event_type not in {"incident.created", "incident.state_changed"}
        or payload.get("event_type") != event.event_type
        or payload.get("event_id") != event.event_id
        or payload.get("aggregate_id") != event.incident_id
        or type(payload.get("event_version")) is not int
        or payload.get("event_version") != 1
    ):
        raise InvalidOutboxEvent("이벤트 종류 또는 식별 정보가 일치하지 않습니다.")
    version = payload.get("aggregate_version")
    if type(version) is not int or version < 1:
        raise InvalidOutboxEvent("인시던트 버전은 양의 정수여야 합니다.")
    try:
        IncidentStatus(payload["to_status"])
        if event.event_type == "incident.state_changed":
            IncidentStatus(payload["from_status"])
        elif payload.get("from_status") is not None:
            raise ValueError("생성 이벤트에는 이전 상태가 없습니다.")
        occurred_at = datetime.fromisoformat(payload["occurred_at"])
        if occurred_at.tzinfo is None:
            raise ValueError("발생 시각에는 시간대가 필요합니다.")
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidOutboxEvent(
            "이벤트 상태 또는 발생 시각이 올바르지 않습니다."
        ) from error
    _log(event, "VALIDATED")


class OutboxWorker:
    """짧은 인수 트랜잭션과 처리 후 결과 기록 트랜잭션을 구분합니다."""

    def __init__(
        self,
        connection: psycopg.Connection,
        processor: Callable[[OutboxEvent], None] = validate_and_log,
        *,
        clock: Callable[[], datetime] | None = None,
        lease_seconds: float = 60,
        retry_seconds: float = 5,
        max_retry_seconds: float = 300,
    ) -> None:
        if any(
            not math.isfinite(value) or value <= 0
            for value in (
                lease_seconds,
                retry_seconds,
                max_retry_seconds,
            )
        ):
            raise ValueError("잠금과 재시도 간격은 0보다 커야 합니다.")
        self.connection = connection
        self.processor = processor
        self.clock = clock or (lambda: datetime.now(UTC))
        self.lease_seconds = lease_seconds
        self.retry_seconds = retry_seconds
        self.max_retry_seconds = max_retry_seconds

    def claim(self) -> OutboxEvent | None:
        now = self.clock()
        with self.connection.transaction():
            self.connection.execute(EXHAUSTED_LEASE_SQL, (now, now))
            row = self.connection.execute(CLAIM_SQL, (now, now)).fetchone()
            if row is None:
                return None
            event = OutboxEvent(
                event_id=str(row[0]),
                incident_id=row[1],
                event_type=row[2],
                payload=row[3],
                attempts=row[4] + 1,
                max_attempts=row[5],
            )
            self.connection.execute(
                START_SQL,
                (now + timedelta(seconds=self.lease_seconds), event.event_id),
            )
        _log(event, "RUNNING")
        return event

    def complete(self, event: OutboxEvent) -> bool:
        now = self.clock()
        with self.connection.transaction():
            row = self.connection.execute(
                COMPLETE_SQL,
                (now, event.event_id, event.attempts, now),
            ).fetchone()
        _log(event, "COMPLETED" if row else "ACK_IGNORED")
        return row is not None

    def fail(self, event: OutboxEvent, error: Exception) -> bool:
        now = self.clock()
        retry = (
            isinstance(error, RetryableProcessingError)
            and event.attempts < event.max_attempts
        )
        status = "PENDING" if retry else "DLQ"
        delay = min(
            self.max_retry_seconds,
            self.retry_seconds * 2 ** min(event.attempts - 1, 20),
        )
        available_at = now + timedelta(seconds=delay) if retry else now
        # 원본 예외에는 연결 정보가 포함될 수 있어 저장소와 로그에 그대로 노출하지 않습니다.
        if retry:
            summary = "일시적인 처리 실패로 재시도를 대기합니다."
        elif isinstance(error, InvalidOutboxEvent):
            summary = "이벤트 계약이 올바르지 않아 실패 보관함에 이동했습니다."
        elif isinstance(error, RetryableProcessingError):
            summary = "최대 시도 횟수에 도달해 실패 보관함에 이동했습니다."
        else:
            summary = "처리 실패로 실패 보관함에 이동했습니다."
        with self.connection.transaction():
            row = self.connection.execute(
                FAIL_SQL,
                (
                    status,
                    available_at,
                    summary,
                    None if retry else now,
                    event.event_id,
                    event.attempts,
                    now,
                ),
            ).fetchone()
        _log(event, status if row else "ACK_IGNORED")
        return row is not None

    def run_once(self) -> bool:
        event = self.claim()
        if event is None:
            return False
        try:
            self.processor(event)
        except Exception as error:  # noqa: BLE001 - 처리기 오류를 실패 보관함으로 격리하는 경계입니다.
            self.fail(event, error)
        else:
            self.complete(event)
        return True

    def run(self, stop: threading.Event, poll_seconds: float = 1) -> None:
        if not math.isfinite(poll_seconds) or poll_seconds <= 0:
            raise ValueError("조회 간격은 0보다 커야 합니다.")
        while not stop.is_set():
            if not self.run_once():
                stop.wait(poll_seconds)


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0 or not math.isfinite(seconds):
        raise argparse.ArgumentTypeError("0보다 큰 유한한 초 단위를 입력해 주세요.")
    return seconds


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="ServIQ Outbox 이벤트를 검증하고 처리 결과를 기록합니다."
    )
    parser.add_argument(
        "--once", action="store_true", help="최대 한 건을 처리하고 종료합니다."
    )
    parser.add_argument(
        "--poll-seconds",
        type=_positive_seconds,
        default=1,
        help="빈 대기열 조회 간격 (초)",
    )
    parser.add_argument(
        "--lease-seconds",
        type=_positive_seconds,
        default=60,
        help="작업 인수 잠금 시간 (초)",
    )
    arguments = parser.parse_args(argv)
    dsn = os.environ.get("SERVIQ_DATABASE_URL")
    if not dsn:
        raise SystemExit("SERVIQ_DATABASE_URL을 설정해 주세요.")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stop = threading.Event()
    previous_handlers = {}

    def request_stop(_signum: int, _frame: Any) -> None:
        stop.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, request_stop)
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = OutboxWorker(connection, lease_seconds=arguments.lease_seconds)
            if arguments.once:
                worker.run_once()
            else:
                worker.run(stop, poll_seconds=arguments.poll_seconds)
    except psycopg.Error:
        raise SystemExit(
            "Outbox 저장소 연결을 확인해 주세요. 잠금 만료 후 작업을 다시 처리할 수 있습니다."
        ) from None
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    main()
