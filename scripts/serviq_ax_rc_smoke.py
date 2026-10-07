"""Day 30 actual PG + Worker + MCP/Loop + human review + AX/RC evidence. No external writes."""
import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from scripts.serviq_multi_agent_smoke import CountHistory, FailInventory, seed

from src.ai.ax.releases import GoldenCaseResult, GoldenComparison, candidate_manifest
from src.ai.execution.models import InternalReviewSimulation
from src.ai.execution.service import VerificationCommands
from src.ai.workflow.runtime import HistoryProcessor, postgres_checkpoint
from src.api.app import create_app
from src.application.security.principal import RequestContext, Role
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)

CASES = (("verification_pass", True, "RESOLVED"), ("verification_fail", False, "REOPENED"),
    ("verification_inconclusive", None, "VERIFYING"), ("approval_reject", None, "ACTION_PROPOSED"),
    ("partial_branch", True, "RESOLVED"), ("missing_evidence", None, "INVESTIGATING"))


class EmptyHistory(CountHistory):
    def search_evidence(self, *args):
        self.calls += 1
        return ()


def verify(dsn, code_sha):
    results = []
    for case, present, expected in CASES:
        p, source, principal, job, incident = seed(dsn, loop=True, closed_loop=True)
        if case == "partial_branch":
            source = FailInventory(dsn)
        search = EmptyHistory(dsn) if case == "missing_evidence" else CountHistory(dsn)
        processor = HistoryProcessor(p, search, lambda: postgres_checkpoint(dsn), source=source, dsn=dsn)
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor), tenant_id=principal.tenant_id)
            assert worker.run_once() and worker.run_once()
        with p.transaction(principal.tenant_id) as uow:
            waiting = uow.agent_runs.by_job(job.job_id)
        reviewer = replace(principal, principal_id="rc-human", roles=frozenset({Role.REVIEWER}))
        identity = LocalIdentityProvider({"operator": principal, "human": reviewer,
            "other": replace(principal, tenant_id="other"),
            "store": replace(principal, store_scope=frozenset({"other"}))}, environment="test")
        app = create_app(p.incidents, identity_provider=identity)
        app.state.access_persistence = p
        client, path = TestClient(app), f"/api/v1/incidents/{incident.id}/ax"
        operator_headers = {"Authorization": "Bearer operator", "Idempotency-Key": "rc-event-"+job.job_id}
        initial = client.get(path, headers=operator_headers)
        assert initial.status_code == 200, initial.text
        if case == "missing_evidence":
            assert not waiting.state.rca_candidates and not waiting.state.capa_proposals
            assert initial.json()["human_action"] == "MORE_EVIDENCE_REQUIRED"
            final = waiting
        else:
            assert waiting.status == "WAITING_APPROVAL" and len(waiting.state.branches) == 3
            assert initial.json()["human_action"] == "APPROVAL_REQUIRED"
            assert initial.json()["execution_mode"] is None
            VerificationCommands(p, waiting.agent_run_id, principal.tenant_id).prepare_simulation(
                RequestContext(principal, "rc-simulation", job.correlation_id),
                InternalReviewSimulation(tenant_id=principal.tenant_id, store=incident.store, agent_run_id=waiting.agent_run_id,
                    source_ref="internal-review:"+str(uuid4()), review_record_present=present,
                    additional_evidence_refs=waiting.state.evidence_refs))
            decision = "reject" if case == "approval_reject" else "approve"
            response = client.post(f"/api/v1/reviews/{waiting.state.approval.approval_id}/{decision}",
                headers={"Authorization": "Bearer human", "Idempotency-Key": "rc-decision-"+job.job_id},
                json={"reason": "합성 Golden 근거 검토", "expected_version": 1})
            assert response.status_code == 200, response.text
            approved_ax = client.get(path, headers=operator_headers).json()
            assert approved_ax["execution_mode"] is None
            if decision == "approve":
                assert "실행 완료는 아닙니다" in approved_ax["brief"]["summary"]
            restored = AccessPersistence(PostgresIncidentRepository(dsn))
            restarted = HistoryProcessor(restored, search, lambda: postgres_checkpoint(dsn), source=source, dsn=dsn)
            with psycopg.connect(dsn, autocommit=True) as connection:
                worker = JobWorker(connection, snapshot_processor(p.incidents, history=restarted), tenant_id=principal.tenant_id)
                assert worker.run_once() and not worker.run_once()
            with restored.transaction(principal.tenant_id) as uow:
                final = uow.agent_runs.get(waiting.agent_run_id)
                if decision == "approve":
                    assert len(uow.executions.evidence(final.state.execution)) == 1
                else:
                    assert final.state.execution is None
        assert final.status == "COMPLETED"
        current = p.incidents.get(incident.id, tenant_id=principal.tenant_id)
        # Rejection follows the existing Domain rule (no execution), never a new RC state machine.
        if case == "approval_reject":
            assert current.status.value in {"ACTION_PROPOSED", "RCA_READY"}
        else:
            assert current.status.value == expected
        view = client.get(path, headers=operator_headers).json()
        assert view["current_phase"] == current.status.value
        assert view["source_run_id"] == final.agent_run_id and view["manifest_reference"]
        assert view["brief"]["headline"] and view["next_action"]["reason"] and view["explanation"]["cannot_verify"]
        if case == "partial_branch":
            assert "INVENTORY" in view["coverage"]["missing"] and view["coverage"]["evidence_count"] >= 3
        if final.state.verification:
            assert view["verification_result"] == final.state.verification.result
            assert view["execution_mode"] == "INTERNAL_RECORD_ONLY"
        for token, status in (("other", 404), ("store", 403)):
            assert client.get(path, headers={"Authorization": "Bearer "+token}).status_code == status
        for forbidden in ("MULTI-RAW-SENTINEL", "raw_prompt", "raw_response", "checkpoint", "delegated_roles", "tenant_id"):
            assert forbidden not in str(view)
        event = client.post(path+"/events", headers=operator_headers, json={"event_type": "ai_brief_viewed"})
        assert event.status_code == 201, event.text
        assert client.post(path+"/events", headers=operator_headers, json={"event_type": "ai_brief_viewed"}).json() == event.json()
        with AccessPersistence(PostgresIncidentRepository(dsn)).transaction(principal.tenant_id) as uow:
            assert len(uow.product_events.history(incident.id)) == 1
            assert not uow.llm_calls.history(incident.id)
            candidate = candidate_manifest(final, uow.decisions.get(final.jev_decision_id), uow.configs.get(final.config_version),
                code_git_sha=code_sha, created_at=datetime.now(UTC))
        results.append(GoldenCaseResult(case_id=case, safety_passed=True, completion_passed=True, ax_passed=True))
        print("[PASS] AX/RC PG Golden "+case+" · actual Worker/restart/MCP/Loop/Approval/AX · external calls/write 0")
    comparison = GoldenComparison(baseline_reference="day29-main-8af6c8e", candidate_id=candidate.candidate_id,
        cases=tuple(results), required_cases=tuple(c[0] for c in CASES),
        metric_availability={m["name"]: m["status"] for m in view["metrics"]})
    assert comparison.passed
    print("[PASS] AX/AI MVP RC six-case PG gate · Production NOT READY")


def main():
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    code_sha = os.environ.get("SERVIQ_RC_CODE_SHA")
    if not dsn or not code_sha:
        raise SystemExit("Set isolated SERVIQ_TEST_DATABASE_URL and actual SERVIQ_RC_CODE_SHA.")
    verify(dsn, code_sha)


if __name__ == "__main__":
    main()
