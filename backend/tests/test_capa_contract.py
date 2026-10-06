from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.ai.workflow.models import CAPAProposal


def proposal(**changes):
    return CAPAProposal(**dict(capa_proposal_id=str(uuid4()), tenant_id="t", store="s", incident_id="i",
        agent_run_id=str(uuid4()), rca_candidate_id=str(uuid4()), risk_level="MEDIUM",
        supporting_evidence_ids=("review:r",), target_reference="i", config_version=1,
        decision_reference="d", **changes))


def test_safe_proposal():
    item = proposal()
    assert item.required_approval and item.verification_criteria and item.status == "PROPOSED"
    with pytest.raises(ValidationError):
        item.risk_level = "LOW"


@pytest.mark.parametrize("changes", [{"verification_criteria": ""}, {"tool_name": "shell"},
    {"raw_response": "secret"}, {"supporting_evidence_ids": []}, {"proposed_action_type": "EXTERNAL_WRITE"}])
def test_invalid_proposal(changes):
    value = proposal().model_dump()
    with pytest.raises(ValidationError):
        CAPAProposal.model_validate({**value, **changes})
