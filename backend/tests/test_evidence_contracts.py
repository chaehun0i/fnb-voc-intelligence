"""근거 계약은 원문·SDK 대신 검증 가능한 참조를 사용합니다."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.ai.workflow.models import NormalizedEvidence, SufficiencyPolicy


def evidence(**changes):
    return NormalizedEvidence(**{"tenant_id": "t", "store": "s", "agent_run_id": str(uuid4()),
        "source_ref": "review:r1", "source_id": "r1", "rank": 1,
        "retrieved_at": datetime(2026, 10, 6, tzinfo=UTC), **changes})


def test_evidence_is_immutable_and_scoped():
    item = evidence()
    with pytest.raises(ValidationError):
        item.rank = 2
    assert item.step_name == "history_investigation"
    assert SufficiencyPolicy().minimum_sources == 2


@pytest.mark.parametrize("changes", [{"raw_voc": "secret"}, {"source_id": "other"},
    {"rank": 0}, {"source_at": datetime(2026, 10, 6, tzinfo=UTC).replace(tzinfo=None)}, {"provenance": ()}])
def test_invalid_evidence_rejected(changes):
    with pytest.raises(ValidationError):
        evidence(**changes)
