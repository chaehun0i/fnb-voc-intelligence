"""근거 부족과 상충은 RCA 실행을 허용하지 않습니다."""
import pytest

from src.agents.models import EvidenceGap, SufficiencyPolicy
from src.agents.sufficiency import evaluate_sufficiency
from tests.test_evidence_contracts import evidence


def support(source="r1", **changes):
    return evidence(source_ref="review:"+source, source_id=source,
        observation_code="RELATED_HISTORY_MATCH", stance="SUPPORTING", **changes)


@pytest.mark.parametrize("items,status,reason", [
    ([], "INSUFFICIENT", "NO_EVIDENCE"),
    ([support()], "INSUFFICIENT", "INSUFFICIENT_SOURCE_COVERAGE"),
    ([support(), support("r2")], "SUFFICIENT", "SUFFICIENT_HISTORY_SUPPORT"),
    ([support(), evidence(stance="CONTRADICTING")], "CONFLICTING", "CONFLICTING_EVIDENCE"),
    ([support(), support()], "INSUFFICIENT", "INSUFFICIENT_SOURCE_COVERAGE"),
    ([evidence(), evidence(source_ref="review:r2", source_id="r2")], "INSUFFICIENT", "INSUFFICIENT_SOURCE_COVERAGE"),
])
def test_deterministic_gate(items, status, reason):
    result = evaluate_sufficiency(items)
    assert result == evaluate_sufficiency(items)
    assert result.status == status and result.reason_codes == (reason,)
    assert result.allows_rca == (status == "SUFFICIENT")


def test_policy_explicit_and_llm_failure_is_not_missing_evidence():
    items = [support(), support("r2")]
    gap = EvidenceGap(code="LLM_POLICY_DENIED")
    result = evaluate_sufficiency(items, (gap,))
    assert result.allows_rca and gap in result.evidence_gaps
    assert not evaluate_sufficiency(items, policy=SufficiencyPolicy(minimum_sources=3)).allows_rca
