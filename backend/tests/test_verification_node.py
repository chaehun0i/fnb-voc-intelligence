from datetime import timedelta
from uuid import uuid4

import pytest

from src.agents.verification_commands import VerificationCommands
from src.agents.verification_contracts import VerificationEvidence
from src.agents.verification_rules import evaluate_verification
from tests.test_internal_execution import approved_run


def verifying_state():
    p, run, state, _ = approved_run()
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    return p, run, c.begin_verification(c.execute(state))


def post_evidence(state, present=True):
    return VerificationEvidence(evidence_id=str(uuid4()), tenant_id=state.tenant_id,
        store=state.capa_proposals[0].store, agent_run_id=state.agent_run_id,
        execution_id=state.execution.execution_id, action_id=state.execution.action_id,
        source_ref="internal-review:"+str(uuid4()), observed_at=state.execution.completed_at,
        review_record_present=present, additional_evidence_refs=state.evidence_refs)


@pytest.mark.parametrize("present,expected", [(True, "PASS"), (False, "FAIL"), (None, "INCONCLUSIVE")])
def test_criteria_and_actual_post_action_evidence(present, expected):
    _, run, state = verifying_state()
    evidence = post_evidence(state, present)
    result = evaluate_verification(state.model_copy(update={"verification_evidence": (evidence,)}), run.started_at)
    assert result.verification.result == expected
    assert result.verification.evidence_ids == (evidence.evidence_id,)


def test_no_post_evidence_never_passes_from_history_or_approval():
    _, run, state = verifying_state()
    result = evaluate_verification(state, run.started_at)
    assert result.verification.result == "INCONCLUSIVE"
    assert result.verification.reason_codes == ("EVIDENCE_MISSING",)


def test_stale_and_conflicting_evidence_is_inconclusive():
    _, run, state = verifying_state()
    first, second = post_evidence(state), post_evidence(state, False)
    stale = first.model_copy(update={"observed_at": run.started_at-timedelta(seconds=1)})
    for evidence, reason in [((stale,), "EVIDENCE_STALE"), ((first, second), "EVIDENCE_CONFLICTING")]:
        result = evaluate_verification(state.model_copy(update={"verification_evidence": evidence}), run.started_at)
        assert result.verification.result == "INCONCLUSIVE" and result.verification.reason_codes == (reason,)


def test_fabricated_or_cross_tenant_reference_is_rejected():
    _, run, state = verifying_state()
    evidence = post_evidence(state)
    for change in ({"tenant_id": "other"}, {"additional_evidence_refs": ("review:fake",)}, {"store": "elsewhere"}):
        with pytest.raises(ValueError):
            evaluate_verification(state.model_copy(update={"verification_evidence": (evidence.model_copy(update=change),)}), run.started_at)
