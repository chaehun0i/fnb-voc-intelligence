"""실행 상태에 원문이나 SDK 객체가 들어가지 않는지 확인합니다."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.ai.workflow.models import EvidenceCandidate, EvidenceGap, Finding


def test_normalized_evidence_contract():
    value = EvidenceCandidate(source_ref="review:sample-1", rank=1,
                              retrieved_at=datetime(2026, 10, 1, tzinfo=UTC))
    assert Finding(evidence_refs=(value.source_ref,)).code == "RELATED_HISTORY_FOUND"
    assert EvidenceGap(code="NO_AUTHORIZED_HISTORY").code == "NO_AUTHORIZED_HISTORY"


@pytest.mark.parametrize("field", ["raw_prompt", "credential", "customer_name", "raw_response"])
def test_sensitive_extra_fields_rejected(field):
    with pytest.raises(ValidationError):
        EvidenceGap(code="NO_AUTHORIZED_HISTORY", **{field: "secret"})


def test_naive_time_and_unsupported_source_rejected():
    with pytest.raises(ValidationError):
        EvidenceCandidate(source_ref="raw document", rank=1, retrieved_at=datetime(2026, 10, 1))  # noqa: DTZ001 — 시간대 누락을 의도적으로 거부합니다.
