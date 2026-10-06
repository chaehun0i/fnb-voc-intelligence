"""JSON Trace도 재구성 시 근거·Config·Decision 무결성을 검증합니다."""
from dataclasses import replace

import pytest
from pydantic import ValidationError

from src.ai.workflow.models import AgentRun, WorkflowState
from tests.test_rca_investigation import node, ready


def test_state_roundtrip_and_invalid_reference_rejected():
    result = node()(ready())
    assert WorkflowState.model_validate_json(result.model_dump_json()) == result
    bad = result.rca_candidates[0].model_copy(update={"supporting_refs": ("review:missing",)})
    with pytest.raises(ValidationError):
        WorkflowState.model_validate(result.model_copy(update={"rca_candidates": (bad,)}).model_dump())


def test_run_lineage_cannot_be_swapped(history_setup):
    persistence, service, context, decision = history_setup
    job = service.enqueue(context, "i", decision.decision_id)
    run, _, _ = service.prepare(job)
    source = node()(ready())
    evidence = tuple(e.model_copy(update={"tenant_id": run.tenant_id, "agent_run_id": run.agent_run_id})
                     for e in source.normalized_evidence)
    candidate = source.rca_candidates[0].model_copy(update={"jev_decision_id": run.jev_decision_id})
    state = run.state.model_copy(update={"normalized_evidence": evidence, "sufficiency": source.sufficiency,
                                        "rca_candidates": (candidate,)})
    with persistence.transaction(run.tenant_id) as uow:
        saved = uow.agent_runs.save(run.model_copy(update={"state": state}))
        assert AgentRun.model_validate_json(saved.model_dump_json()) == saved
        bad = candidate.model_copy(update={"jev_decision_id": "other"})
        with pytest.raises(ValidationError):
            uow.agent_runs.save(run.model_copy(update={"state": state.model_copy(update={"rca_candidates": (bad,)})}))
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=2, parent_version=1), 1)
    restored, _, _ = service.prepare(job)
    assert restored.state == state and restored.config_version == 1
