from dataclasses import replace

import pytest
from pydantic import ValidationError

from src.ai.ax.models import AIBrief
from src.ai.ax.projector import project_incident
from src.api.app import demo_incidents


def test_empty_projection_is_honest_and_has_no_numeric_confidence():
    result = project_incident(demo_incidents()[0])
    assert result.source_run_id is None and result.coverage.evidence_count == 0
    assert result.brief.confidence_level == "INCONCLUSIVE" and result.verification_result is None
    assert result.current_phase == "DETECTED"
    assert "raw_prompt" not in result.model_dump_json()
    assert result == project_incident(replace(demo_incidents()[0], title="SECRET-PII"))


def test_ax_contract_rejects_probability_and_extra_sensitive_fields():
    for extra in ({"confidence_level": .99}, {"raw_prompt": "secret"}):
        with pytest.raises(ValidationError):
            AIBrief(headline="안내", summary="상태", **extra)
