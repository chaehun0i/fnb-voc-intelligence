import pytest

from src.application.security.principal import Principal, RequestContext, Role
from src.application.workflows.verification import VerificationCommands
from tests.test_verification_node import post_evidence, verifying_state


@pytest.mark.parametrize("present,result,status", [(True, "PASS", "RESOLVED"),
    (False, "FAIL", "REOPENED"), (None, "INCONCLUSIVE", "VERIFYING")])
def test_application_applies_existing_domain_rules_atomically_and_replays(present, result, status):
    p, run, state = verifying_state()
    context = RequestContext(Principal("operator", "t", frozenset({Role.HQ_ADMIN})), "r", "c")
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    evidence = post_evidence(state, present)
    c.record_evidence(context, evidence, p.incidents.get("i").version)
    candidate = c.evaluate(state)
    assert candidate.verification.result == result
    applied = c.apply(candidate)
    assert c.apply(candidate) == applied
    assert p.incidents.get("i").status == status
    assert p.incidents.get("i").verification.evidence_refs == (evidence.evidence_id,)
    assert p.incidents.get("i").status != "CLOSED"
