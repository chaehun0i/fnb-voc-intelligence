"""Small, explicit retry policy for transient scale-job failures."""

from collections.abc import Callable


class TransientJobError(RuntimeError):
    """An operation may succeed when attempted again later."""


def retry_transient[Result](
    operation: Callable[[], Result],
    retries: int,
    sleep: Callable[[float], None],
) -> Result:
    """Retry transient errors with capped exponential delays only."""
    if retries < 0:
        raise ValueError("retries must not be negative")
    for attempt in range(retries + 1):
        try:
            return operation()
        except TransientJobError:
            if attempt == retries:
                raise
            sleep(min(2**attempt, 30))
    raise AssertionError("unreachable")
