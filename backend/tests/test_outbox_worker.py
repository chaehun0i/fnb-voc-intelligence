"""실제 DB나 외부 서비스 없이 작업 잠금과 재시도 경계를 검증합니다."""

import logging
import signal
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.infrastructure.jobs import outbox_worker as worker_module
from src.infrastructure.jobs.outbox_worker import (
    CLAIM_SQL,
    COMPLETE_SQL,
    EXHAUSTED_LEASE_SQL,
    FAIL_SQL,
    START_SQL,
    InvalidOutboxEvent,
    OutboxEvent,
    OutboxWorker,
    RetryableProcessingError,
    main,
    validate_and_log,
)

NOW = datetime(2026, 10, 2, 9, tzinfo=UTC)
EVENT_ID = "11111111-1111-4111-8111-111111111111"


def event(attempts: int = 1, max_attempts: int = 3) -> OutboxEvent:
    return OutboxEvent(
        EVENT_ID,
        "inc-1",
        "incident.state_changed",
        {
            "event_id": EVENT_ID,
            "aggregate_id": "inc-1",
            "event_type": "incident.state_changed",
            "event_version": 1,
            "aggregate_version": 2,
            "from_status": "DETECTED",
            "to_status": "TRIAGED",
            "occurred_at": "2026-10-02T09:00:00Z",
            "correlation_id": "inc-1",
        },
        attempts,
        max_attempts,
    )


def row(attempts: int = 0, max_attempts: int = 3) -> tuple:
    value = event(attempts, max_attempts)
    return (
        UUID(value.event_id),
        value.incident_id,
        value.event_type,
        value.payload,
        value.attempts,
        value.max_attempts,
    )


class FakeResult:
    def __init__(self, value: tuple | None) -> None:
        self.value = value

    def fetchone(self) -> tuple | None:
        return self.value


class FakeConnection:
    def __init__(self, responses: list[tuple | None]) -> None:
        self.responses = list(responses)
        self.queries: list[tuple[str, tuple]] = []
        self.transactions = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield

    def execute(self, query: str, params: tuple) -> FakeResult:
        self.queries.append((query, params))
        return FakeResult(self.responses.pop(0))


def test_claim_uses_short_locked_transaction_and_attempt_token() -> None:
    connection = FakeConnection([None, row(1), None])
    claimed = OutboxWorker(connection, clock=lambda: NOW, lease_seconds=30).claim()
    assert claimed == event(2)
    assert connection.transactions == 1
    assert connection.queries == [
        (EXHAUSTED_LEASE_SQL, (NOW, NOW)),
        (CLAIM_SQL, (NOW, NOW)),
        (START_SQL, (NOW + timedelta(seconds=30), EVENT_ID)),
    ]
    assert "FOR UPDATE SKIP LOCKED" in CLAIM_SQL
    assert "status='RUNNING' AND lease_until <=" in CLAIM_SQL
    assert "attempts < max_attempts" in CLAIM_SQL
    assert "attempts >= max_attempts" in EXHAUSTED_LEASE_SQL


def test_empty_queue_has_no_processing_side_effect() -> None:
    connection = FakeConnection([None, None])
    assert not OutboxWorker(connection, clock=lambda: NOW).run_once()
    assert len(connection.queries) == 2


def test_success_processing_occurs_outside_claim_transaction() -> None:
    connection = FakeConnection([None, row(), None, (EVENT_ID,)])
    received: list[OutboxEvent] = []

    def processor(value: OutboxEvent) -> None:
        assert connection.transactions == 1
        received.append(value)

    assert OutboxWorker(connection, processor, clock=lambda: NOW).run_once()
    assert received == [event()]
    assert connection.transactions == 2
    assert connection.queries[-1] == (COMPLETE_SQL, (NOW, EVENT_ID, 1, NOW))


@pytest.mark.parametrize("attempts, expected_delay", [(1, 5), (2, 10), (8, 30)])
def test_temporary_failure_uses_bounded_backoff(attempts, expected_delay) -> None:
    connection = FakeConnection([(EVENT_ID,)])
    worker = OutboxWorker(connection, clock=lambda: NOW, max_retry_seconds=30)
    assert worker.fail(event(attempts, 10), RetryableProcessingError("secret"))
    query, params = connection.queries[-1]
    assert query == FAIL_SQL
    assert params[0] == "PENDING"
    assert params[1] == NOW + timedelta(seconds=expected_delay)
    assert params[3] is None
    assert params[4:] == (EVENT_ID, attempts, NOW)
    assert "secret" not in params[2]


@pytest.mark.parametrize(
    "failure", [ValueError("bad payload"), RetryableProcessingError("unavailable")]
)
def test_terminal_or_exhausted_failure_is_sent_to_dlq(failure) -> None:
    connection = FakeConnection([(EVENT_ID,)])
    assert OutboxWorker(connection, clock=lambda: NOW).fail(event(3), failure)
    params = connection.queries[-1][1]
    assert params[0] == "DLQ"
    assert params[1] == NOW
    assert params[3] == NOW


def test_unexpected_processor_failure_is_recorded_in_dlq() -> None:
    connection = FakeConnection([None, row(), None, (EVENT_ID,)])

    def processor(_event: OutboxEvent) -> None:
        raise ValueError("malformed event")

    assert OutboxWorker(connection, processor, clock=lambda: NOW).run_once()
    assert connection.queries[-1][0] == FAIL_SQL
    assert connection.queries[-1][1][0] == "DLQ"


def test_expired_or_reclaimed_worker_cannot_ack_a_new_attempt() -> None:
    connection = FakeConnection([None, None])
    worker = OutboxWorker(connection, clock=lambda: NOW)
    assert not worker.complete(event())
    assert not worker.fail(event(), RetryableProcessingError())
    assert "attempts=%s AND lease_until > %s" in COMPLETE_SQL
    assert "attempts=%s AND lease_until > %s" in FAIL_SQL


def test_default_processor_validates_contract_and_logs_no_payload(caplog) -> None:
    with caplog.at_level(logging.INFO):
        validate_and_log(event())
    assert '"status": "VALIDATED"' in caplog.text
    assert EVENT_ID in caplog.text
    assert "from_status" not in caplog.text


@pytest.mark.parametrize(
    "patch",
    [
        {"event_version": 2},
        {"event_type": "unknown"},
        {"aggregate_id": "other"},
        {"aggregate_version": True},
        {"to_status": "unknown"},
        {"from_status": "unknown"},
        {"occurred_at": "2026-10-02T09:00:00"},
    ],
)
def test_default_processor_rejects_invalid_contract(patch) -> None:
    value = event()
    value.payload.update(patch)
    with pytest.raises(InvalidOutboxEvent):
        validate_and_log(value)


def test_run_waits_on_empty_queue_and_stops_without_claiming_again() -> None:
    connection = FakeConnection([None, None])

    class Stop(threading.Event):
        def wait(self, timeout=None):
            assert timeout == 0.2
            self.set()
            return True

    OutboxWorker(connection, clock=lambda: NOW).run(Stop(), poll_seconds=0.2)
    assert len(connection.queries) == 2


def test_shutdown_during_processing_records_result_before_exit() -> None:
    connection = FakeConnection([None, row(), None, (EVENT_ID,)])
    stop = threading.Event()

    def processor(_event: OutboxEvent) -> None:
        stop.set()

    OutboxWorker(connection, processor, clock=lambda: NOW).run(stop)
    assert connection.queries[-1][0] == COMPLETE_SQL
    assert len(connection.queries) == 4


def test_cli_once_uses_explicit_transactions_and_restores_handlers(monkeypatch) -> None:
    connection = FakeConnection([None, row(), None, (EVENT_ID,)])
    handlers = []

    def connect(dsn, *, autocommit):
        assert dsn == "postgresql://localhost/serviq_test"
        assert autocommit is True
        return connection

    def install_handler(signum, handler):
        handlers.append((signum, handler))
        return signal.SIG_DFL

    monkeypatch.setenv("SERVIQ_DATABASE_URL", "postgresql://localhost/serviq_test")
    monkeypatch.setattr(worker_module.psycopg, "connect", connect)
    monkeypatch.setattr(worker_module.signal, "signal", install_handler)
    main(["--once"])
    assert connection.transactions == 2
    assert connection.queries[-1][0] == COMPLETE_SQL
    assert handlers[-2:] == [(signal.SIGINT, signal.SIG_DFL), (signal.SIGTERM, signal.SIG_DFL)]


def test_cli_requires_explicit_serviq_database_url(monkeypatch) -> None:
    monkeypatch.delenv("SERVIQ_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="SERVIQ_DATABASE_URL"):
        main(["--once"])


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_cli_rejects_invalid_poll_interval(value, monkeypatch) -> None:
    monkeypatch.delenv("SERVIQ_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as raised:
        main(["--poll-seconds", value])
    assert raised.value.code == 2
