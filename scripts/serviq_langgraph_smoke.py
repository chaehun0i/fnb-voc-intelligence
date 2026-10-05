"""전용 PostgreSQL에서 실제 검색·Checkpoint 중단/복구·Trace를 검증합니다."""
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres import PostgresSaver

from src.api.app import create_app
from src.application.decisions.shadow import ShadowDecisions
from src.application.security.principal import Principal, RequestContext, Role
from src.application.workflows.history import HistoryWorkflows
from src.data.database import initialize_schema
from src.data.models import Product, Review
from src.data.repositories import bulk_insert_reviews, insert_product
from src.domain.config.models import ConfigVersion, LLMModelBinding, RuntimeConfig
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Evidence, Incident
from src.domain.jobs.models import Job
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.history_search import PostgresHistorySearch
from src.infrastructure.migrations import migrate
from src.infrastructure.queue.runtime import snapshot_processor
from src.infrastructure.queue.worker import JobWorker
from src.infrastructure.repositories.job_repository import PostgresJobRepository
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)
from src.llm.execution import RoutedLLMExecutor
from src.llm.providers.fake import FakeProvider
from src.llm.router import ProviderRouter
from src.rag.embeddings import FakeEmbeddingProvider
from src.rag.indexing import index_reviews
from src.runtime.workflows.checkpoint import postgres_checkpoint
from src.runtime.workflows.processor import HistoryProcessor


class FakeGemini(FakeProvider):
    capability = FakeProvider.capability.model_copy(update={"provider": "gemini", "hosted": True})


class FailHistoryCheckpoint(PostgresSaver):
    def __init__(self, saver):
        super().__init__(saver.conn, serde=saver.serde)
        self.failed = False

    def put(self, config, checkpoint, metadata, new_versions):
        state = checkpoint.get("channel_values", {}).get("snapshot", {})
        if not self.failed and state.get("iteration", 0) == 1 and state.get("status") == "RUNNING":
            self.failed = True
            raise psycopg.OperationalError("CHECKPOINT_FAULT_INJECTION")
        return super().put(config, checkpoint, metadata, new_versions)


def verify(dsn):
    migrate(dsn)
    migrate(dsn)
    now = datetime.now(UTC)
    tenant = "history-"+uuid4().hex
    principal = Principal("operator", tenant, frozenset({Role.HQ_ADMIN}))
    repo = PostgresIncidentRepository(dsn)
    persistence = AccessPersistence(repo)
    incident = repo.save(Incident(str(uuid4()), "HISTORY-SMOKE", "quality", Severity.MEDIUM,
        IncidentStatus.INVESTIGATING, "store-a", "담당", now.isoformat(), now.isoformat(), tenant_id=tenant,
        evidence=[Evidence("history-ref", "source", "HISTORY", "참조", .9)]))
    config = RuntimeConfig(jev_enabled=True, auto_investigation=True, auto_rca_draft=True,
        allowed_tools=("voc.search",), hosted_ai_allowed=True, llm_enabled_providers=("gemini",),
        llm_models=(LLMModelBinding("gemini", "FAST", "fake-contract-only", 1, 2),))
    with persistence.transaction(tenant) as uow:
        uow.configs.append(ConfigVersion(1, tenant, config, "durable 검증", "operator", now), 0)
        snapshot = uow.jobs.save(Job(str(uuid4()), tenant, "incident.snapshot", "history-smoke", now, now,
                                    incident_id=incident.id, store=incident.store))
    decision = ShadowDecisions(persistence).record(snapshot)
    assert decision.result.requires_llm and "HISTORY" in decision.result.investigation_agents
    service = HistoryWorkflows(persistence)
    context = RequestContext(principal, "history-request", "history-correlation")
    job = service.enqueue(context, incident.id, decision.decision_id)
    assert service.enqueue(context, incident.id, decision.decision_id) == job
    product_id, review_id, excluded_id = "product-"+uuid4().hex, "review-"+uuid4().hex, "excluded-"+uuid4().hex
    embedding = FakeEmbeddingProvider()
    with psycopg.connect(dsn) as connection:
        initialize_schema(connection)
        cursor = connection.cursor()
        insert_product(cursor, Product(product_id=product_id, brand="synthetic", product_name="검증 제품",
            category="quality", price=1, weight_g=1, calories_kcal=1, protein_g=0, carbohydrate_g=0,
            sugar_g=0, fat_g=0, sodium_mg=0, source="synthetic"))
        reviews = [Review(review_id=rid, product_id=product_id, rating=1,
            review_text="quality PII-SENTINEL customer@example.com", review_date=date(2026, 10, 5), source="synthetic")
                   for rid in (review_id, excluded_id)]
        bulk_insert_reviews(cursor, reviews)
        assert index_reviews(cursor, reviews, embedding, 10).indexed == 2
        connection.execute("INSERT INTO serviq_history_sources(tenant_id,store,review_id) VALUES(%s,%s,%s)", (tenant, "store-a", review_id))
    search = PostgresHistorySearch(dsn, embedding)
    assert search.search(tenant, "store-a", "quality") == [("review:"+review_id, 1)]
    assert search.search(tenant+"-other", "store-a", "quality") == []
    assert search.search(tenant, "store-b", "quality") == []
    fake = FakeGemini(['{"needs_more_history":false}'])
    factory = lambda record: RoutedLLMExecutor(ProviderRouter({"gemini": fake}), recorder=record)
    @contextmanager
    def broken_checkpoint():
        with postgres_checkpoint(dsn) as saver:
            yield FailHistoryCheckpoint(saver)
    failed_processor = HistoryProcessor(persistence, search, broken_checkpoint, dsn=dsn, executor_factory=factory)
    with psycopg.connect(dsn, autocommit=True) as connection:
        # 기존 snapshot Job은 먼저 처리하고 History claim을 분리합니다.
        worker = JobWorker(connection, snapshot_processor(repo, history=failed_processor), tenant_id=tenant,
                           retry_seconds=.001, clock=lambda: datetime.now(UTC)+timedelta(seconds=1))
        assert worker.run_once()
        assert worker.run_once()
        assert PostgresJobRepository(connection, tenant).get(job.job_id).status == "PENDING"
    with persistence.transaction(tenant) as uow:
        first = uow.agent_runs.by_job(job.job_id)
        assert first.status == "FAILED" and first.state.iteration == 1
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=2, parent_version=1, config=RuntimeConfig()), 1)
    # 프로세스 재시작과 같이 Repository·Application·Saver를 새로 만들고 재개합니다.
    restored_persistence = AccessPersistence(PostgresIncidentRepository(dsn))
    restored = HistoryProcessor(restored_persistence, search, lambda: postgres_checkpoint(dsn),
                               dsn=dsn, executor_factory=factory)
    with psycopg.connect(dsn, autocommit=True) as connection:
        worker = JobWorker(connection, snapshot_processor(repo, history=restored), tenant_id=tenant,
                           clock=lambda: datetime.now(UTC)+timedelta(seconds=1))
        assert worker.run_once()
        assert PostgresJobRepository(connection, tenant).get(job.job_id).status == "COMPLETED"
        assert not worker.run_once()
    with restored_persistence.transaction(tenant) as uow:
        final = uow.agent_runs.by_job(job.job_id)
        assert final.agent_run_id == first.agent_run_id and final.status == "COMPLETED"
        assert final.config_version == 1 and final.state.token_spent == 15
        assert len(uow.agent_runs.history(incident.id)) == 1 and len(uow.llm_calls.history(incident.id)) == 1
        assert len(uow.agent_runs.steps(final.agent_run_id)) >= 3
    assert fake.call_count == 1 and repo.get(incident.id) == incident
    with postgres_checkpoint(dsn) as saver:
        saved = saver.get_tuple({"configurable": {"thread_id": final.workflow_id}})
        assert saved.checkpoint["channel_values"]["snapshot"]["status"] == "COMPLETED"
        assert "PII-SENTINEL" not in str(saved.checkpoint)
    identity = LocalIdentityProvider({"a": principal, "b": replace(principal, tenant_id=tenant+"-other"),
        "store": replace(principal, store_scope=frozenset({"elsewhere"}))}, environment="test")
    client = TestClient(create_app(PostgresIncidentRepository(dsn), identity_provider=identity))
    path = f"/api/v1/incidents/{incident.id}/agent-runs"
    headers = {"Authorization": "Bearer a"}
    response = client.get(path+"/"+final.agent_run_id, headers=headers)
    assert response.status_code == 200 and response.json()["evidence_candidates"][0]["source_ref"] == "review:"+review_id
    assert "PII-SENTINEL" not in response.text and excluded_id not in response.text
    assert client.get(path, headers={"Authorization": "Bearer b"}).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    assert client.post(path, headers=headers).status_code == 405
    with psycopg.connect(dsn, autocommit=True) as connection:
        try:
            with connection.transaction():
                connection.execute("UPDATE serviq_agent_steps SET document=document WHERE tenant_id=%s", (tenant,))
        except psycopg.errors.RaiseException:
            pass
        else:
            raise AssertionError("단계 감사는 수정할 수 없어야 합니다.")
    print("[통과] LangGraph 실제 PostgreSQL·hybrid/pgvector 출처 격리·Checkpoint 실패/재시작·LLM 1회·Config 고정·Trace·Tenant/store·PII 미노출")


def main():
    dsn = os.getenv("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("검증 전용 SERVIQ_TEST_DATABASE_URL을 명시해 주세요.")
    verify(dsn)


if __name__ == "__main__":
    main()
