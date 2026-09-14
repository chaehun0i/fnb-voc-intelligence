import pytest

from src.rag.retry import TransientJobError, retry_transient


def test_retries_transient_error_with_exponential_backoff() -> None:
    calls = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientJobError("temporary")
        return "ok"

    assert retry_transient(operation, retries=3, sleep=delays.append) == "ok"
    assert delays == [1, 2]


def test_does_not_retry_permanent_error() -> None:
    delays: list[float] = []
    with pytest.raises(ValueError, match="invalid"):
        retry_transient(
            lambda: (_ for _ in ()).throw(ValueError("invalid")),
            retries=3,
            sleep=delays.append,
        )
    assert delays == []


def test_stops_after_retry_limit() -> None:
    with pytest.raises(TransientJobError):
        retry_transient(
            lambda: (_ for _ in ()).throw(TransientJobError("temporary")),
            retries=1,
            sleep=lambda _delay: None,
        )
