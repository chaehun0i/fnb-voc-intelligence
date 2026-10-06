from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.workflows.verification import (
    ActionExecutionRecord,
    VerificationEvidence,
)


def execution():
    now = datetime(2026, 10, 6, tzinfo=UTC)
    return ActionExecutionRecord(execution_id=str(uuid4()), tenant_id="t", incident_id="i",
        agent_run_id=str(uuid4()), action_id="a", approval_id="p", action_digest="a"*64,
        started_at=now, completed_at=now, config_version=1, correlation_id="c", incident_version=2)


@pytest.mark.parametrize("change", [{"execution_mode": "EXTERNAL"}, {"raw_response": "secret"},
    {"completed_at": datetime(2026, 10, 5, tzinfo=UTC)}, {"started_at": datetime(2026, 10, 6, tzinfo=UTC).replace(tzinfo=None)}])
def test_execution_rejects_unsafe_or_invalid_contract(change):
    with pytest.raises(ValidationError):
        ActionExecutionRecord.model_validate({**execution().model_dump(), **change})


def test_verification_source_is_separate_from_history_and_generated_text():
    e = execution()
    values = {"evidence_id": str(uuid4()), "tenant_id": "t", "store": "s", "agent_run_id": e.agent_run_id,
        "execution_id": e.execution_id, "action_id": "a", "source_ref": "internal-review:"+str(uuid4()),
        "observed_at": e.completed_at, "review_record_present": True, "additional_evidence_refs": ("review:1",)}
    assert VerificationEvidence(**values).observation_mode == "SIMULATED"
    with pytest.raises(ValidationError):
        VerificationEvidence(**{**values, "source_type": "LLM_RESPONSE"})
