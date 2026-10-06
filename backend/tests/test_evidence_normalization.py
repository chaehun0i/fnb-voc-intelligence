"""중복 출처는 합치되 조직·매장과 provenance를 보존합니다."""
from uuid import uuid4

import pytest

from src.ai.workflow.agents import normalize_evidence
from src.ai.workflow.models import EvidenceCandidate
from src.application.security.principal import AccessError
from tests.test_evidence_contracts import evidence as normalized_example


def evidence(**changes):
    return EvidenceCandidate.model_validate(normalized_example(**changes).model_dump(
        exclude={"agent_run_id", "source_id", "step_name"}))


def normalize(items):
    return normalize_evidence(items, tenant_id="t", store="s", agent_run_id=str(uuid4()))


def test_dedup_preserves_provenance():
    one = evidence(provenance=("lexical",), rank=2)
    two = one.model_copy(update={"provenance": ("vector",), "rank": 1})
    result = normalize([one, two])
    assert len(result) == 1 and result[0].rank == 1
    assert result[0].provenance == ("lexical", "vector")
    assert result[0].source_id == "r1" and result[0].stance == "NEUTRAL"


@pytest.mark.parametrize("changes", [{"tenant_id": "other"}, {"store": "other"}, {"tenant_id": None}])
def test_scope_mismatch_is_not_silently_accepted(changes):
    with pytest.raises(AccessError):
        normalize([evidence().model_copy(update=changes)])


def test_conflicting_same_source_not_overwritten():
    one = evidence()
    with pytest.raises(ValueError):
        normalize([one, one.model_copy(update={"stance": "CONTRADICTING"})])
