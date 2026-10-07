from datetime import UTC, datetime

import pytest

from src.ai.ax.releases import (
    GoldenCaseResult,
    GoldenComparison,
    ReleaseCandidate,
    candidate_manifest,
)
from tests.test_loop_harness import loop_setup


def test_candidate_reuses_pinned_manifest_and_checks_lineage():
    persistence, _, run, _ = loop_setup()
    with persistence.transaction(run.tenant_id) as uow:
        decision, config = uow.decisions.get(run.jev_decision_id), uow.configs.get(run.config_version)
    candidate = candidate_manifest(run, decision, config, code_git_sha="a"*40, created_at=datetime.now(UTC))
    assert candidate.run_manifest == run.manifest and candidate.status == "EVALUATION_CANDIDATE"
    assert candidate.model_route_config_version == run.config_version
    assert "production" not in candidate.model_dump_json()
    with pytest.raises(ValueError, match="DIGEST"):
        ReleaseCandidate.model_validate(candidate.model_dump() | {"manifest_digest": "0"*64})
    with pytest.raises(ValueError, match="LINEAGE"):
        candidate_manifest(run.model_copy(update={"manifest": None}), decision, config,
            code_git_sha="a"*40, created_at=datetime.now(UTC))


def test_rc_gate_rejects_missing_scenarios_or_any_safety_blocker():
    case = GoldenCaseResult(case_id="pass", safety_passed=True, completion_passed=True, ax_passed=True)
    comparison = GoldenComparison(baseline_reference="day29-main", candidate_id="candidate", cases=(case,), required_cases=("pass",))
    assert comparison.passed
    assert not comparison.model_copy(update={"required_cases": ("pass", "fail")}).passed
    assert not comparison.model_copy(update={"cases": (case.model_copy(update={"blockers": ("HARNESS_BYPASS",)}),)}).passed
