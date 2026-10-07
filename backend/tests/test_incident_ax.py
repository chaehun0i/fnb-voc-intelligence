from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.ai.ax.actions import next_action
from src.ai.ax.explanations import explain
from src.ai.ax.models import AIBrief
from src.ai.ax.projector import project_incident
from src.api.app import create_app, demo_incidents
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider


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


def test_ax_api_is_scoped_and_separate_from_trace(history_setup):
    persistence, service, context, decision = history_setup
    job = service.enqueue(context, "i", decision.decision_id)
    run, _, _ = service.prepare(job)
    identity = LocalIdentityProvider({"reader": context.principal,
        "other": replace(context.principal, tenant_id="other"),
        "store": replace(context.principal, store_scope=frozenset({"elsewhere"}))}, environment="test")
    app = create_app(persistence.incidents, identity_provider=identity)
    app.state.access_persistence = persistence
    client = TestClient(app)
    path = "/api/v1/incidents/i/ax"
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"Authorization": "Bearer reader"})
    assert response.status_code == 200
    assert response.json()["source_run_id"] == run.agent_run_id
    assert response.json()["decision_reference"] == decision.decision_id
    for secret in ("checkpoint", "raw_prompt", "tenant_id", "delegated_roles", "requested_by"):
        assert secret not in response.text
    assert client.get(path, headers={"Authorization": "Bearer other"}).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    assert client.post(path, headers={"Authorization": "Bearer reader"}).status_code == 405


@pytest.mark.parametrize("updates,kwargs,human,action", [
    ({"approval_status": "PENDING"}, {}, "APPROVAL_REQUIRED", "OPEN_REVIEW"),
    ({"approval_status": "APPROVED"}, {}, "REVIEW_REQUIRED", "CHECK_RESULT"),
    ({"approval_status": "REJECTED"}, {}, "REVIEW_REQUIRED", "MANUAL_REVIEW"),
    ({"current_phase": "VERIFYING"}, {}, "VERIFICATION_REQUIRED", "VERIFY"),
    ({}, {"termination": "BUDGET_EXHAUSTED"}, "BUDGET_INCREASE_REQUIRED", "MANUAL_REVIEW"),
    ({}, {"termination": "NO_NEW_EVIDENCE"}, "MORE_EVIDENCE_REQUIRED", "COLLECT_EVIDENCE"),
    ({}, {"uncertain_effect": True}, "MANUAL_TAKEOVER_RECOMMENDED", "MANUAL_REVIEW"),
    ({}, {"control": "STOPPED"}, "REVIEW_REQUIRED", "MANUAL_REVIEW"),
    ({"current_phase": "RESOLVED"}, {}, "NONE", "CHECK_RESULT"),
])
def test_human_actions_do_not_invent_execution_or_retry(updates, kwargs, human, action):
    view = project_incident(demo_incidents()[0]).model_copy(update=updates)
    result = next_action(view, **kwargs)
    assert result.human_action == human and result.next_action.action_type == action
    assert result.next_action.risk == view.next_action.risk
    if action != "CHECK_RESULT":
        assert not result.next_action.permission and result.next_action.blocking_reason


def test_pending_approval_uses_review_permission():
    view = project_incident(demo_incidents()[0]).model_copy(update={"approval_status": "PENDING"})
    assert not next_action(view, operate=True).next_action.permission
    assert next_action(view, review=True).next_action.permission


@pytest.mark.parametrize("result,phase,message", [
    ("PASS", "RESOLVED", "충족했습니다"), ("FAIL", "REOPENED", "재조사가 필요"),
    ("INCONCLUSIVE", "VERIFYING", "검증 상태를 유지"),
])
def test_explanation_separates_verification_from_real_world_effect(result, phase, message):
    view = project_incident(demo_incidents()[0]).model_copy(update={"current_phase": phase,
        "execution_mode": "INTERNAL_RECORD_ONLY", "verification_result": result})
    result = explain(view)
    assert message in result.brief.summary and "외부 시스템은 변경하지 않았습니다" in result.brief.summary
    assert result.explanation.cannot_verify and not result.explanation.technical_trace_available


def test_brief_never_describes_approval_as_execution():
    view = project_incident(demo_incidents()[0]).model_copy(update={"approval_status": "APPROVED"})
    assert "실행 완료는 아닙니다" in explain(view).brief.summary


def test_ax_controls_reuse_current_runtime_and_preserve_manifest():
    from src.ai.ax.service import IncidentAXQueries
    from src.application.agent_controls import AgentControls
    from src.application.security.principal import RequestContext
    from tests.test_loop_harness import loop_setup
    persistence, _, run, _ = loop_setup()
    from src.application.security.principal import Principal
    principal = Principal(run.requested_by, run.tenant_id, frozenset(run.delegated_roles), frozenset(run.delegated_store_scope))
    context = RequestContext(principal, "ax-control", "ax-control", "ax-pause")
    query = IncidentAXQueries(persistence, context)
    before = query.get(run.incident_id)
    assert before.runtime.permissions["pause"]
    AgentControls(persistence).execute(context, run.incident_id, run.agent_run_id, "pause", 0)
    after = query.get(run.incident_id)
    assert after.runtime.control_status == "PAUSED" and after.runtime.control_version == 1
    assert not after.runtime.permissions["pause"] and after.runtime.permissions["resume"]
    assert before.manifest_reference == after.manifest_reference and before.coverage == after.coverage
