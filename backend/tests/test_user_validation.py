from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.ai.ax.validation import ValidationSession, validation_task


def session(**changes):
    now = datetime(2026, 10, 9, tzinfo=UTC)
    values = {"session_id": uuid4(), "tenant_id": "tenant", "store_id": "store",
        "scenario_id": "happy_path", "participant_ref": uuid4(), "started_at": now,
        "created_at": now, "validation_kind": "SYNTHETIC"}
    return ValidationSession(**(values | changes))


def test_session_is_opaque_immutable_and_business_task():
    item = session()
    assert item.consent_scope == "TASK_EVENTS_ONLY"
    assert validation_task("happy_path").expected_terminal_state == "RESOLVED"
    assert "Checkpoint" not in validation_task("happy_path").business_goal
    with pytest.raises(ValidationError):
        item.status = "COMPLETED"
    with pytest.raises(ValidationError):
        session(participant_ref="person@example.com")
    with pytest.raises(ValidationError):
        session(raw_prompt="secret")


@pytest.mark.parametrize("changes", [{"status": "COMPLETED"},
    {"started_at": "2026-01-01T00:00:00"},
    {"status": "ABANDONED", "completed_at": datetime(2026, 10, 8, tzinfo=UTC)}])
def test_session_rejects_incoherent_timestamps(changes):
    with pytest.raises(ValidationError):
        session(**changes)


def test_terminal_session_requires_real_terminal_time():
    item = session()
    completed = session(status="COMPLETED", completed_at=item.started_at + timedelta(seconds=20))
    assert completed.completed_at > completed.started_at
