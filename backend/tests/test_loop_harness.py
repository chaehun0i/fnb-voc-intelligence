from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.ai.workflow.models import LoopPolicy
from src.ai.workflow.policy import evidence_digest, loop_policy, loop_termination
from src.domain.config.models import RuntimeConfig


def test_loop_policy_uses_server_caps_and_existing_counters():
    policy = loop_policy(RuntimeConfig(max_agent_iterations=20))
    assert policy.max_iterations == 3
    now = datetime.now(UTC)
    state = SimpleNamespace(iteration=1, tool_call_count=3, token_spent=0, cost_spent=0,
        evidence_refs=("review:one",))
    assert loop_termination(policy, state, now=now, started_at=now) is None
    assert loop_termination(policy, state, now=now, started_at=now,
        before_refs=("review:one",)) == "NO_NEW_EVIDENCE"
    state.iteration = 3
    assert loop_termination(policy, state, now=now, started_at=now) == "ITERATION_LIMIT"
    state.tool_call_count = policy.max_operations
    assert loop_termination(policy, state, now=now, started_at=now) == "BUDGET_EXHAUSTED"
    state.tool_call_count = 0
    assert loop_termination(policy, state, now=now+timedelta(seconds=120), started_at=now) == "BUDGET_EXHAUSTED"


@pytest.mark.parametrize("field,value", [("max_iterations", 4), ("max_operations", -1),
    ("token_budget", True), ("cost_budget", float("inf")), ("timeout_seconds", 601)])
def test_invalid_budget_rejected(field, value):
    values = loop_policy(RuntimeConfig()).model_dump()
    with pytest.raises(ValidationError):
        LoopPolicy(**(values | {field: value}))


def test_canonical_evidence_digest_is_order_and_duplicate_independent():
    assert evidence_digest(("review:a", "review:b", "review:a")) == evidence_digest(("review:b", "review:a"))
