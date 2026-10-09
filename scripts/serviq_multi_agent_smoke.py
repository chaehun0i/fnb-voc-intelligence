"""격리 PostgreSQL의 실제 검색/Send/checkpoint/branch 기록을 검증합니다. 외부 호출 없음."""
import argparse
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from scripts.serviq_langgraph_smoke import FailHistoryCheckpoint

from src.ai.ax.service import AgentRunQueries
from src.ai.decision.engine import JevEngine, build_context
from src.ai.decision.models import AgentType, Category, DecisionRecord
from src.ai.execution.models import InternalReviewSimulation
from src.ai.execution.service import VerificationCommands
from src.ai.workflow.agents import SourceUnavailable
from src.ai.workflow.models import OperationalObservation
from src.ai.workflow.runtime import (
    HistoryProcessor,
    HistoryWorkflows,
    postgres_checkpoint,
)
from src.api.app import create_app
from src.application.security.principal import Principal, RequestContext, Role
from src.data.database import initialize_schema
from src.data.models import Product, Review
from src.data.repositories import bulk_insert_reviews, insert_product
from src.domain.config.models import ConfigVersion, RuntimeConfig
from src.domain.config.resolution import ConfigResolver
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Evidence, Incident
from src.domain.jobs.models import Job
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.history_search import PostgresHistorySearch
from src.infrastructure.investigation_source import PostgresInvestigationSource
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.migrations import migrate
from src.infrastructure.repositories.job_repository import PostgresJobRepository
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def seed(dsn, *, inventory=True, tenant=None, closed_loop=False, loop=False, max_operations=20, sample_dataset=False):
    migrate(dsn)
    now, suffix = datetime.now(UTC), uuid4().hex
    tenant = tenant or "multi-"+suffix
    principal = Principal("multi-operator", tenant, frozenset({Role.HQ_ADMIN}))
    persistence = AccessPersistence(PostgresIncidentRepository(dsn))
    incident = persistence.incidents.save(Incident(str(uuid4()), "MULTI-SMOKE", "품질" if sample_dataset else "quality", Severity.MEDIUM,
        IncidentStatus.INVESTIGATING, "multi-store-"+suffix, "담당", now.isoformat(), now.isoformat(),
        tenant_id=tenant, evidence=[Evidence("history-ref", "synthetic", "HISTORY", "참조", .9)]))
    with psycopg.connect(dsn) as connection:
        initialize_schema(connection)
        cursor = connection.cursor()
        product = "multi-product-"+suffix
        insert_product(cursor, Product(product_id=product, brand="synthetic", product_name="검증 제품", category="quality",
            price=1, weight_g=1, calories_kcal=1, protein_g=0, carbohydrate_g=0, sugar_g=0, fat_g=0, sodium_mg=0, source="synthetic"))
        reviews = [Review(review_id="multi-review-"+suffix+str(i), product_id=product, rating=1,
            review_text="quality MULTI-RAW-SENTINEL", review_date=now.date(), source="synthetic") for i in (1, 2)]
        bulk_insert_reviews(cursor, reviews)
        for review in (() if sample_dataset else reviews):
            connection.execute("INSERT INTO serviq_history_sources(tenant_id,store,review_id) VALUES(%s,%s,%s)",
                (tenant, incident.store, review.review_id))
        for agent in (() if sample_dataset else ("TRANSACTION", "INVENTORY") if inventory else ("TRANSACTION",)):
            observation = OperationalObservation(tenant_id=tenant, store=incident.store, agent_type=agent,
                source_ref=agent.lower()+":"+suffix, observed_at=now,
                signal="REFUND_SIGNAL" if agent == "TRANSACTION" else "STOCK_SHORTAGE")
            connection.execute("INSERT INTO serviq_operational_observations(tenant_id,store,agent_type,source_ref,observed_at,document) VALUES(%s,%s,%s,%s,%s,%s)",
                (tenant, incident.store, agent, observation.source_ref, now, Jsonb(observation.model_dump(mode="json"))))
    with persistence.transaction(tenant) as uow:
        previous = uow.configs.current()
        config = RuntimeConfig(jev_enabled=True, auto_investigation=True, auto_rca_draft=True, multi_agent_enabled=True,
            loop_enabled=loop, max_tool_calls=max_operations,
            auto_capa_draft=closed_loop, internal_execution_enabled=closed_loop,
            allowed_tools=("voc.search", "transaction.search", "inventory.snapshot"), hosted_ai_allowed=False,
            llm_enabled_providers=(), llm_models=())
        version = previous.config_version+1 if previous else 1
        uow.configs.append(ConfigVersion(version, tenant, config, "합성 Multi-Agent 검증", principal.principal_id, now,
            previous.config_version if previous else None), version-1)
        # Golden의 canonical category/data availability를 실제 Jev pure engine에 입력합니다.
        context = replace(build_context(incident, ConfigResolver().resolve(config), version), category=Category.GENERAL,
            data_availability=(AgentType.HISTORY, AgentType.TRANSACTION, AgentType.INVENTORY))
        snapshot = uow.jobs.save(Job(str(uuid4()), tenant, "incident.snapshot", "multi-golden-"+suffix,
            now, now, incident_id=incident.id, store=incident.store))
        decision = DecisionRecord(str(uuid4()), tenant, incident.id, snapshot.job_id,
            JevEngine().evaluate(context), "a"*64, now, 0, incident.version)
        uow.decisions.append(decision)
    source = PostgresInvestigationSource(dsn)
    service = HistoryWorkflows(persistence, source=source)
    job = service.enqueue(RequestContext(principal, "multi-seed", "multi-"+suffix), incident.id, decision.decision_id)
    assert service.enqueue(RequestContext(principal, "multi-seed", "multi-"+suffix), incident.id, decision.decision_id) == job
    return persistence, source, principal, job, incident


class CountHistory(PostgresHistorySearch):
    calls = 0

    def search_evidence(self, *args):
        self.calls += 1
        return super().search_evidence(*args)


class FailInventory(PostgresInvestigationSource):
    def observations(self, context):
        if context.agent_type == "INVENTORY":
            raise SourceUnavailable("MUST-NOT-LEAK")
        return super().observations(context)


def verify(dsn):
    for scenario in ("all", "partial", "filter", "restart"):
        p, source, principal, job, incident = seed(dsn, inventory=scenario != "filter")
        search = CountHistory(dsn)
        if scenario == "partial":
            source = FailInventory(dsn)
        @contextmanager
        def checkpoint():
            with postgres_checkpoint(dsn) as saver:
                yield saver
        processor = HistoryProcessor(p, search, checkpoint, source=source, dsn=dsn)
        if scenario == "restart":
            @contextmanager
            def broken():
                with postgres_checkpoint(dsn) as saver:
                    yield FailHistoryCheckpoint(saver)
            failed = HistoryProcessor(p, search, broken, source=source, dsn=dsn)
            with psycopg.connect(dsn, autocommit=True) as connection:
                worker = JobWorker(connection, snapshot_processor(p.incidents, history=failed),
                    tenant_id=principal.tenant_id, retry_seconds=.001)
                assert worker.run_once() and worker.run_once()
                assert PostgresJobRepository(connection, principal.tenant_id).get(job.job_id).status == "PENDING"
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor),
                tenant_id=principal.tenant_id, retry_seconds=.001, clock=lambda: datetime.now(UTC)+timedelta(seconds=1))
            assert worker.run_once()
            if scenario != "restart":
                assert worker.run_once()
            assert PostgresJobRepository(connection, principal.tenant_id).get(job.job_id).status == "COMPLETED"
        with p.transaction(principal.tenant_id) as uow:
            run = uow.agent_runs.by_job(job.job_id)
        assert run.status == "COMPLETED" and run.workflow_version == "multi-investigation-v5"
        assert len(run.state.branches) == (2 if scenario == "filter" else 3)
        assert run.state.sufficiency.status == "SUFFICIENT" and run.state.rca_candidates
        assert len(run.state.normalized_evidence) == (4 if scenario in {"all", "restart"} else 3)
        if scenario in {"partial", "filter"}:
            assert any(g.agent_type == "INVENTORY" for g in run.state.evidence_gaps)
        assert HistoryWorkflows(p, source=source).prepare(job)[0] == run and search.calls == 1
        restored = AccessPersistence(PostgresIncidentRepository(dsn))
        with restored.transaction(principal.tenant_id) as uow:
            assert uow.agent_runs.get(run.agent_run_id) == run
            for branch in run.state.branches:
                assert uow.agent_runs.append_branch(run.agent_run_id, branch) == branch
        with restored.transaction(principal.tenant_id+"-other") as uow:
            assert uow.agent_runs.get(run.agent_run_id) is None
            assert uow.agent_runs.branch(run.agent_run_id, "HISTORY") is None
        detail = AgentRunQueries(restored, principal).execute(incident.id, run_id=run.agent_run_id)
        assert detail["investigation"]["status"] == ("PARTIAL" if scenario in {"partial", "filter"} else "COMPLETED")
        assert restored.incidents.get(incident.id, tenant_id=principal.tenant_id) == incident
        assert not any(v in json.dumps(detail) for v in ("MULTI-RAW-SENTINEL", "MUST-NOT-LEAK", "raw_prompt", "delegated_roles", "context_digest"))
        identity = LocalIdentityProvider({"reader": principal, "other": replace(principal, tenant_id="other"),
            "store": replace(principal, store_scope=frozenset({"other-store"}))}, environment="test")
        app = create_app(p.incidents, identity_provider=identity)
        app.state.access_persistence = restored
        client = TestClient(app)
        path = "/api/v1/incidents/"+incident.id+"/agent-runs/"+run.agent_run_id
        assert client.get(path, headers={"Authorization": "Bearer reader"}).status_code == 200
        assert client.get(path, headers={"Authorization": "Bearer other"}).status_code == 404
        assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
        print("[통과] Multi-Agent PostgreSQL Golden "+scenario+" · scoped search/branch/fan-in/RCA/restart/dedup · 외부 호출 0")
    verify_closed_loop(dsn)


def verify_closed_loop(dsn):
    for present, final in ((True, "RESOLVED"), (False, "REOPENED"), (None, "VERIFYING")):
        p, source, principal, job, incident = seed(dsn, closed_loop=True)
        search = CountHistory(dsn)
        processor = HistoryProcessor(p, search, lambda: postgres_checkpoint(dsn), source=source, dsn=dsn)
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor), tenant_id=principal.tenant_id)
            assert worker.run_once() and worker.run_once()
        with p.transaction(principal.tenant_id) as uow:
            waiting = uow.agent_runs.by_job(job.job_id)
        assert waiting.status == "WAITING_APPROVAL" and len(waiting.state.branches) == 3
        VerificationCommands(p, waiting.agent_run_id, principal.tenant_id).prepare_simulation(
            RequestContext(principal, "multi-verification", job.correlation_id),
            InternalReviewSimulation(tenant_id=principal.tenant_id, store=incident.store, agent_run_id=waiting.agent_run_id,
                source_ref="internal-review:"+str(uuid4()), review_record_present=present,
                additional_evidence_refs=waiting.state.evidence_refs))
        reviewer = replace(principal, principal_id="human-reviewer", roles=frozenset({Role.REVIEWER}))
        app = create_app(p.incidents, identity_provider=LocalIdentityProvider({"human": reviewer}, environment="test"))
        app.state.access_persistence = p
        path = "/api/v1/reviews/"+waiting.state.approval.approval_id+"/approve"
        headers = {"Authorization": "Bearer human", "Idempotency-Key": "multi-approve-"+job.job_id}
        body = {"reason": "합성 운영 근거 검토 승인", "expected_version": 1}
        client = TestClient(app)
        approved = client.post(path, json=body, headers=headers)
        assert approved.status_code == 200, approved.text
        assert client.post(path, json=body, headers=headers).json() == approved.json()
        restored = AccessPersistence(PostgresIncidentRepository(dsn))
        restarted = HistoryProcessor(restored, search, lambda: postgres_checkpoint(dsn), source=source, dsn=dsn)
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(p.incidents, history=restarted), tenant_id=principal.tenant_id)
            assert worker.run_once() and not worker.run_once()
        with restored.transaction(principal.tenant_id) as uow:
            run = uow.agent_runs.get(waiting.agent_run_id)
            assert run.status == "COMPLETED" and uow.incidents.get(incident.id).status == final
            assert len(uow.executions.evidence(run.state.execution)) == 1
            assert not uow.llm_calls.history(incident.id)
        assert run.state.execution.execution_mode == "INTERNAL_RECORD_ONLY" and search.calls == 1
        print("[통과] Multi-Agent→기존 CAPA/Approval→재시작/resume→내부 실행/Verification→"+final+" · 외부 호출/변경 0")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-http", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("격리 검증 DB의 SERVIQ_TEST_DATABASE_URL을 명시해 주세요.")
    if args.seed_http:
        _, _, _, job, incident = seed(dsn, tenant="legacy-local")
        print(json.dumps({"incident_id": incident.id, "job_id": job.job_id}))
    else:
        verify(dsn)


if __name__ == "__main__":
    main()
