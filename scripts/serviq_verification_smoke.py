"""외부 AI/시스템 변경 없는 실제 PostgreSQL Golden Closed Loop 3종."""
import argparse
import json
import os
from dataclasses import replace
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from scripts.serviq_langgraph_smoke import seed_capa_http

from src.ai.execution.models import InternalReviewSimulation
from src.ai.execution.service import VerificationCommands
from src.ai.workflow.runtime import RESUME_JOB, HistoryProcessor, postgres_checkpoint
from src.api.app import create_app
from src.application.security.principal import Principal, RequestContext, Role
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.history_search import PostgresHistorySearch
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)
from src.rag.embeddings import FakeEmbeddingProvider

CASES = ((True, "PASS", "RESOLVED"), (False, "FAIL", "REOPENED"), (None, "INCONCLUSIVE", "VERIFYING"))


def processor(dsn, *, claimed=True):
    persistence = AccessPersistence(PostgresIncidentRepository(dsn))
    def no_llm(_):
        raise AssertionError("Golden 검증에서 외부 AI를 호출할 수 없습니다.")
    return HistoryProcessor(persistence, PostgresHistorySearch(dsn, FakeEmbeddingProvider()),
        lambda: postgres_checkpoint(dsn), dsn=dsn if claimed else None, executor_factory=no_llm)


def prepare(dsn, present, *, run_worker=True):
    fixture = seed_capa_http(dsn, internal_execution=True)
    repo = PostgresIncidentRepository(dsn)
    persistence = AccessPersistence(repo)
    if run_worker:
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(repo, history=processor(dsn)), tenant_id="legacy-local")
            for _ in range(100):
                with persistence.transaction("legacy-local") as uow:
                    run = uow.agent_runs.by_job(fixture["job_id"])
                if run and run.status == "WAITING_APPROVAL":
                    break
                assert worker.run_once(), "승인 대기 전에 Worker가 처리할 Job이 없습니다."
        assert run.status == "WAITING_APPROVAL"
        prepare_review(dsn, run, present)
        return {**fixture, "agent_run_id": run.agent_run_id}
    return fixture


def prepare_review(dsn, run, present):
    context = RequestContext(Principal("simulation-operator", "legacy-local", frozenset({Role.HQ_ADMIN})), "golden-source", run.correlation_id)
    persistence = AccessPersistence(PostgresIncidentRepository(dsn))
    with persistence.transaction("legacy-local") as uow:
        store = uow.incidents.get(run.incident_id).store
    VerificationCommands(persistence, run.agent_run_id, "legacy-local").prepare_simulation(context,
        InternalReviewSimulation(tenant_id="legacy-local", store=store, agent_run_id=run.agent_run_id,
            source_ref="internal-review:"+str(uuid4()), review_record_present=present,
            additional_evidence_refs=run.state.evidence_refs))


def verify(dsn):
    for present, outcome, final_status in CASES:
        fixture = prepare(dsn, present)
        # 새로운 Repository/Graph/DB connection으로 실제 대기 Checkpoint를 복원합니다.
        repo = PostgresIncidentRepository(dsn)
        persistence = AccessPersistence(repo)
        reviewer = Principal("human-reviewer", "legacy-local", frozenset({Role.REVIEWER}))
        identity = LocalIdentityProvider({"human": reviewer, "other": replace(reviewer, tenant_id="other"),
            "store": replace(reviewer, store_scope=frozenset({"elsewhere"}))}, environment="test")
        client = TestClient(create_app(repo, identity_provider=identity))
        with persistence.transaction("legacy-local") as uow:
            run = uow.agent_runs.get(fixture["agent_run_id"])
            approval = uow.approvals.get(run.state.approval.approval_id)
        with postgres_checkpoint(dsn) as saver:
            assert saver.get_tuple({"configurable": {"thread_id": run.workflow_id}}) is not None
        headers = {"Authorization": "Bearer human", "Idempotency-Key": "golden-"+run.agent_run_id}
        path = f"/api/v1/reviews/{approval.approval_id}/approve"
        body = {"reason": "합성 기록 검토 승인", "expected_version": approval.version}
        approved = client.post(path, json=body, headers=headers)
        assert approved.status_code == 200, approved.text
        assert client.post(path, json=body, headers=headers).json() == approved.json()
        with persistence.transaction("legacy-local") as uow:
            jobs = uow.jobs.list(job_type=RESUME_JOB, incident_id=run.incident_id)
            assert len(jobs) == 1
        restored = processor(dsn)
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(repo, history=restored), tenant_id="legacy-local")
            for _ in range(100):
                with persistence.transaction("legacy-local") as uow:
                    final = uow.agent_runs.get(run.agent_run_id)
                if final.status == "COMPLETED":
                    break
                assert worker.run_once()
        assert final.state.verification.result == outcome and repo.get(run.incident_id).status == final_status
        # Worker는 완료 Job을 다시 claim하지 않습니다. 완료 결과의 Application
        # replay는 새 lease가 아닌 동일 durable business identity로 검증합니다.
        assert processor(dsn, claimed=False)(jobs[0]) == final
        with AccessPersistence(PostgresIncidentRepository(dsn)).transaction("legacy-local") as uow:
            assert uow.executions.get(run.agent_run_id) == final.state.execution
            assert len(uow.executions.evidence(final.state.execution)) == 1
            assert len(uow.agent_runs.history(run.incident_id)) == 1
            assert [s.sequence for s in uow.agent_runs.steps(run.agent_run_id)] == list(range(1, 16))
            assert not uow.llm_calls.history(run.incident_id)
        detail = f"/api/v1/incidents/{run.incident_id}/agent-runs/{run.agent_run_id}"
        response = client.get(detail, headers=headers)
        assert response.status_code == 200 and response.json()["resulting_incident_status"] == final_status
        assert response.json()["execution"]["execution_mode"] == "INTERNAL_RECORD_ONLY"
        assert client.get(detail, headers={"Authorization": "Bearer other"}).status_code == 404
        assert client.get(detail, headers={"Authorization": "Bearer store"}).status_code == 403
        assert not any(s in response.text for s in ("SYNTHETIC-RAW-SENTINEL", "raw_prompt", "raw_response", "delegated_roles", "tenant_id"))
        with postgres_checkpoint(dsn) as saver:
            checkpoint = saver.get_tuple({"configurable": {"thread_id": run.workflow_id}})
            assert checkpoint.checkpoint["channel_values"]["snapshot"]["verification"]["result"] == outcome
            assert "SYNTHETIC-RAW-SENTINEL" not in str(checkpoint)
        print(f"[통과] Golden {outcome}→{final_status} · PG/승인/재시작/checkpoint/중복/Trace · 외부 호출 0 · SIMULATED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-http", choices=["PASS", "FAIL", "INCONCLUSIVE"])
    parser.add_argument("--prepare-http", help="승인 대기 AgentRun의 합성 검토 입력 준비")
    parser.add_argument("--outcome", choices=["PASS", "FAIL", "INCONCLUSIVE"])
    args = parser.parse_args()
    dsn = os.getenv("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("검증 전용 SERVIQ_TEST_DATABASE_URL을 명시해 주세요.")
    if args.seed_http:
        present = {"PASS": True, "FAIL": False, "INCONCLUSIVE": None}[args.seed_http]
        print(json.dumps({**prepare(dsn, present), "outcome": args.seed_http}))
    elif args.prepare_http:
        with AccessPersistence(PostgresIncidentRepository(dsn)).transaction("legacy-local") as uow:
            run = uow.agent_runs.get(args.prepare_http)
        prepare_review(dsn, run, {"PASS": True, "FAIL": False, "INCONCLUSIVE": None}[args.outcome])
    else:
        verify(dsn)


if __name__ == "__main__":
    main()
