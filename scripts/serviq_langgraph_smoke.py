"""전용 PostgreSQL에서 실제 검색·Checkpoint 중단/복구·Trace를 검증합니다."""
import argparse
import json
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
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.migrations import migrate
from src.infrastructure.repositories.job_repository import PostgresJobRepository
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)
from src.infrastructure.workflows.checkpoint import postgres_checkpoint
from src.infrastructure.workflows.processor import HistoryProcessor
from src.llm.execution import RoutedLLMExecutor
from src.llm.providers.fake import FakeProvider
from src.llm.router import ProviderRouter
from src.rag.embeddings import FakeEmbeddingProvider
from src.rag.indexing import index_reviews


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
    verify_evidence_rca(dsn, persistence, repo, incident, principal, config, review_id, excluded_id)
    verify_approval_workflow(dsn, persistence, repo, incident, principal, config)


class FailRCACheckpoint(PostgresSaver):
    def __init__(self, saver):
        super().__init__(saver.conn, serde=saver.serde)
        self.failed = False

    def put(self, config, checkpoint, metadata, new_versions):
        state = checkpoint.get("channel_values", {}).get("snapshot", {})
        if not self.failed and state.get("rca_completed") and state.get("status") == "RUNNING":
            self.failed = True
            raise psycopg.OperationalError("RCA_CHECKPOINT_FAULT_INJECTION")
        return super().put(config, checkpoint, metadata, new_versions)


def verify_evidence_rca(dsn, persistence, repo, incident, principal, config, review_id, second_id):
    tenant, now = principal.tenant_id, datetime.now(UTC)
    with psycopg.connect(dsn) as connection:
        connection.execute("INSERT INTO serviq_history_sources(tenant_id,store,review_id) VALUES(%s,%s,%s)",
                           (tenant, incident.store, second_id))
    with persistence.transaction(tenant) as uow:
        previous = uow.configs.current()
        active = replace(config, llm_models=(*config.llm_models,
                         LLMModelBinding("gemini", "STANDARD", "fake-rca-only", 1, 2)))
        uow.configs.append(ConfigVersion(3, tenant, active, "Evidence/RCA 검증", "operator", now, 2), previous.config_version)
        snapshot = uow.jobs.save(Job(str(uuid4()), tenant, "incident.snapshot", "rca-smoke", now, now,
                                    incident_id=incident.id, store=incident.store))
    decision = ShadowDecisions(persistence).record(snapshot)
    service = HistoryWorkflows(persistence)
    job = service.enqueue(RequestContext(principal, "rca-request", "rca-correlation"), incident.id, decision.decision_id)
    refs = sorted(["review:"+review_id, "review:"+second_id])
    fake = FakeGemini(['{"needs_more_history":false}', json.dumps({"code": "REPEATED_HISTORY_SIGNAL",
                                                              "supporting_refs": refs, "confidence": .5})])
    factory = lambda record: RoutedLLMExecutor(ProviderRouter({"gemini": fake}), recorder=record)
    search = PostgresHistorySearch(dsn, FakeEmbeddingProvider())
    @contextmanager
    def broken():
        with postgres_checkpoint(dsn) as saver:
            yield FailRCACheckpoint(saver)
    processor = HistoryProcessor(persistence, search, broken, dsn=dsn, executor_factory=factory)
    with psycopg.connect(dsn, autocommit=True) as connection:
        worker = JobWorker(connection, snapshot_processor(repo, history=processor), tenant_id=tenant,
                           retry_seconds=.001, clock=lambda: datetime.now(UTC)+timedelta(seconds=1))
        assert worker.run_once() and worker.run_once()
        assert PostgresJobRepository(connection, tenant).get(job.job_id).status == "PENDING"
    with persistence.transaction(tenant) as uow:
        failed = uow.agent_runs.by_job(job.job_id)
        assert failed.status == "FAILED" and failed.state.rca_completed and len(failed.state.rca_candidates) == 1
        uow.configs.append(ConfigVersion(4, tenant, RuntimeConfig(), "실행 중 정책 변경 검증", "operator", now, 3), 3)
    restored_persistence = AccessPersistence(PostgresIncidentRepository(dsn))
    restored = HistoryProcessor(restored_persistence, search, lambda: postgres_checkpoint(dsn), dsn=dsn, executor_factory=factory)
    with psycopg.connect(dsn, autocommit=True) as connection:
        worker = JobWorker(connection, snapshot_processor(repo, history=restored), tenant_id=tenant,
                           clock=lambda: datetime.now(UTC)+timedelta(seconds=1))
        assert worker.run_once()
        assert PostgresJobRepository(connection, tenant).get(job.job_id).status == "COMPLETED"
        assert not worker.run_once()
    with restored_persistence.transaction(tenant) as uow:
        final = uow.agent_runs.by_job(job.job_id)
        assert final.agent_run_id == failed.agent_run_id and final.config_version == 3
        assert final.state.sufficiency.status == "SUFFICIENT" and len(final.state.normalized_evidence) == 2
        assert final.state.rca_candidates[0].supporting_refs == tuple(refs)
        assert final.state.token_spent == 30 and final.state.iteration == 2
        assert {s.node_name for s in uow.agent_runs.steps(final.agent_run_id)} == {
            "validate_context", "history_investigation", "normalize_evidence", "evaluate_sufficiency", "rca_investigation", "persist_result"}
    assert fake.call_count == 2 and repo.get(incident.id) == incident
    with postgres_checkpoint(dsn) as saver:
        checkpoint = saver.get_tuple({"configurable": {"thread_id": final.workflow_id}})
        assert checkpoint.checkpoint["channel_values"]["snapshot"]["rca_completed"]
        assert "PII-SENTINEL" not in str(checkpoint.checkpoint)
    identity = LocalIdentityProvider({"a": principal, "b": replace(principal, tenant_id=tenant+"-other")}, environment="test")
    client = TestClient(create_app(PostgresIncidentRepository(dsn), identity_provider=identity))
    path = f"/api/v1/incidents/{incident.id}/agent-runs/{final.agent_run_id}"
    response = client.get(path, headers={"Authorization": "Bearer a"})
    assert response.status_code == 200 and response.json()["rca_candidates"][0]["supporting_refs"] == refs
    assert client.get(path, headers={"Authorization": "Bearer b"}).status_code == 404
    assert not any(value in response.text for value in ("PII-SENTINEL", "customer@example.com", "tenant_id", "raw_prompt"))
    print("[통과] Evidence 2건·provenance·Sufficiency·RCA·RCA Checkpoint 실패/재시작·호출 각 1회·Config v3 고정·Incident 불변·실제 Trace API")


def verify_approval_workflow(dsn, persistence, repo, original, principal, config):
    """기존 History 검색 fixture로 실제 승인 대기/재시작/승인·반려를 검증합니다."""
    from src.application.workflows.resume import RESUME_JOB
    tenant, now = principal.tenant_id, datetime.now(UTC)
    active = replace(config, auto_capa_draft=True, hosted_ai_allowed=False,
                     llm_enabled_providers=(), llm_models=())
    with persistence.transaction(tenant) as uow:
        previous = uow.configs.current()
        uow.configs.append(ConfigVersion(5, tenant, active, "CAPA 승인 대기 검증", "operator", now, 4), previous.config_version)
    search = PostgresHistorySearch(dsn, FakeEmbeddingProvider())
    def no_llm(_):
        raise AssertionError("결정적 CAPA smoke는 외부 LLM을 호출할 수 없습니다.")
    for decision, phase in (("approve", "READY_TO_EXECUTE"), ("reject", "REJECTED")):
        incident = repo.save(replace(original, id=str(uuid4()), display_id="CAPA-SMOKE",
            version=0, created_at=datetime.now(UTC).isoformat()))
        with persistence.transaction(tenant) as uow:
            snapshot = uow.jobs.save(Job(str(uuid4()), tenant, "incident.snapshot", "approval-smoke", now, now,
                                        incident_id=incident.id, store=incident.store))
        jev = ShadowDecisions(persistence).record(snapshot)
        assert not jev.result.requires_llm
        job = HistoryWorkflows(persistence).enqueue(RequestContext(principal, "capa-request", "capa-correlation"),
                                                    incident.id, jev.decision_id)
        processor = HistoryProcessor(persistence, search, lambda: postgres_checkpoint(dsn), dsn=dsn,
                                     executor_factory=no_llm)
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(repo, history=processor), tenant_id=tenant)
            assert worker.run_once() and worker.run_once()
            assert PostgresJobRepository(connection, tenant).get(job.job_id).status == "COMPLETED"
        with persistence.transaction(tenant) as uow:
            waiting = uow.agent_runs.by_job(job.job_id)
            assert waiting.status == "WAITING_APPROVAL" and waiting.completed_at is None
            assert waiting.state.sufficiency.status == "SUFFICIENT" and len(waiting.state.capa_proposals) == 1
            approval = uow.approvals.get(waiting.state.approval.approval_id)
            assert approval.status == "PENDING" and approval.agent_run_id == waiting.agent_run_id
            assert uow.incidents.get(incident.id).status == "PENDING_APPROVAL"
        # 단계 9가 존재하는 DB에서 과거 CHECK 상한을 재적용하지 않아야 합니다.
        migrate(dsn)
        restored = AccessPersistence(PostgresIncidentRepository(dsn))
        with postgres_checkpoint(dsn) as saver:
            checkpoint = saver.get_tuple({"configurable": {"thread_id": waiting.workflow_id}})
            assert checkpoint.checkpoint["channel_values"]["snapshot"]["status"] == "WAITING_APPROVAL"
            assert "PII-SENTINEL" not in str(checkpoint)
        reviewer = Principal("human-reviewer", tenant, frozenset({Role.REVIEWER}))
        identity = LocalIdentityProvider({"reader": reviewer,
            "other": replace(reviewer, tenant_id=tenant+"-other"),
            "store": replace(reviewer, store_scope=frozenset({"elsewhere"})),
            "audit": replace(reviewer, roles=frozenset({Role.AUDITOR}))}, environment="test")
        client = TestClient(create_app(PostgresIncidentRepository(dsn), identity_provider=identity))
        headers = {"Authorization": "Bearer reader", "Idempotency-Key": "approval-"+incident.id}
        path = f"/api/v1/reviews/{approval.approval_id}/{decision}"
        body = {"reason": "담당자가 근거와 검증 기준을 확인했습니다.", "expected_version": approval.version}
        assert client.post(path, json=body, headers={**headers, "Authorization": "Bearer other"}).status_code == 404
        assert client.post(path, json=body, headers={**headers, "Authorization": "Bearer store"}).status_code == 403
        assert client.post(path, json=body, headers={**headers, "Authorization": "Bearer audit"}).status_code == 403
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert client.post(path, json=body, headers=headers).json() == response.json()
        assert client.post(path, json={**body, "reason": "다른 내용"}, headers=headers).status_code == 409
        with restored.transaction(tenant) as uow:
            jobs = uow.jobs.list(job_type=RESUME_JOB, incident_id=incident.id)
            assert len(jobs) == 1
            assert uow.agent_runs.get(waiting.agent_run_id).config_version == 5
        resumed = HistoryProcessor(restored, search, lambda: postgres_checkpoint(dsn), dsn=dsn, executor_factory=no_llm)
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(repo, history=resumed), tenant_id=tenant)
            assert worker.run_once() and not worker.run_once()
            assert PostgresJobRepository(connection, tenant).get(jobs[0].job_id).status == "COMPLETED"
        with restored.transaction(tenant) as uow:
            final = uow.agent_runs.get(waiting.agent_run_id)
            assert final.status == "COMPLETED" and final.state.approval.phase == phase
            assert final.config_version == 5 and len(uow.agent_runs.history(incident.id)) == 1
            assert len(uow.approvals.list(incident.id)) == 1 and not uow.llm_calls.history(incident.id)
            assert all(a.status != "EXECUTED" for a in uow.incidents.get(incident.id).corrective_actions)
            assert [s.sequence for s in uow.agent_runs.steps(final.agent_run_id)] == list(range(1, 12))
        detail = client.get(f"/api/v1/incidents/{incident.id}/agent-runs/{final.agent_run_id}", headers=headers)
        assert detail.status_code == 200 and detail.json()["approval"]["phase"] == phase
        assert not any(v in detail.text for v in ("PII-SENTINEL", "customer@example.com", "delegated_roles", "raw_prompt", "raw_response"))
    print("[통과] 실제 CAPA Command·Approval·interrupt·PostgreSQL 재시작·승인/반려·resume Job·중복 방지·외부 실행 없음·Trace")


def main():
    parser = argparse.ArgumentParser(description="격리된 DB에서 History/CAPA durable workflow를 검증합니다.")
    parser.add_argument("--seed-capa-http", action="store_true", help="nginx 검증용 안전한 opt-in Job fixture를 준비합니다.")
    args = parser.parse_args()
    dsn = os.getenv("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("검증 전용 SERVIQ_TEST_DATABASE_URL을 명시해 주세요.")
    if args.seed_capa_http:
        print(json.dumps(seed_capa_http(dsn)))
    else:
        verify(dsn)


def seed_capa_http(dsn, *, internal_execution=False):
    """공개 실행 API 없이 검증 전용 Application에서 Job만 등록합니다."""
    from src.application.incidents.service import IncidentService
    migrate(dsn)
    now, suffix = datetime.now(UTC), uuid4().hex
    principal = Principal("http-workflow-requester", "legacy-local", frozenset({Role.HQ_ADMIN}))
    repo = PostgresIncidentRepository(dsn)
    persistence = AccessPersistence(repo)
    with persistence.transaction(principal.tenant_id) as uow:
        previous = uow.configs.current()
        config = replace(previous.config if previous else RuntimeConfig(), jev_enabled=True,
            auto_investigation=True, auto_rca_draft=True, auto_capa_draft=True,
            internal_execution_enabled=internal_execution,
            allowed_tools=("voc.search",), hosted_ai_allowed=False, llm_enabled_providers=(),
            llm_models=(), separation_of_duties=True, required_roles=("REVIEWER", "HQ_ADMIN"))
        version = (previous.config_version if previous else 0)+1
        uow.configs.append(ConfigVersion(version, principal.tenant_id, config, "격리 HTTP CAPA 검증",
            principal.principal_id, now, previous.config_version if previous else None), version-1)
        service = IncidentService(uow.incidents, principal=principal)
        item = service.create("quality", Severity.MEDIUM, "http-capa-"+suffix, "synthetic")
        item = service.triage(item.id, expected_version=item.version)
        item = service.investigate(item.id, item.version)
        item = service.add_evidence(item.id, Evidence("history-ref", "synthetic", "HISTORY", "이력 참조", .9), item.version)
        snapshot = uow.jobs.save(Job(str(uuid4()), principal.tenant_id, "incident.snapshot", item.id,
            now, now, incident_id=item.id, store=item.store))
    with psycopg.connect(dsn) as connection:
        initialize_schema(connection)
        cursor = connection.cursor()
        product_id = "http-product-"+suffix
        insert_product(cursor, Product(product_id=product_id, brand="synthetic", product_name="검증 제품",
            category="quality", price=1, weight_g=1, calories_kcal=1, protein_g=0, carbohydrate_g=0,
            sugar_g=0, fat_g=0, sodium_mg=0, source="synthetic"))
        reviews = [Review(review_id="http-review-"+suffix+str(index), product_id=product_id, rating=1,
            review_text="quality SYNTHETIC-RAW-SENTINEL", review_date=now.date(), source="synthetic") for index in (1, 2)]
        bulk_insert_reviews(cursor, reviews)
        for review in reviews:
            connection.execute("INSERT INTO serviq_history_sources(tenant_id,store,review_id) VALUES(%s,%s,%s)",
                (principal.tenant_id, item.store, review.review_id))
    decision = ShadowDecisions(persistence).record(snapshot)
    assert not decision.result.requires_llm
    job = HistoryWorkflows(persistence).enqueue(RequestContext(principal, "http-capa-seed", item.id), item.id, decision.decision_id)
    return {"incident_id": item.id, "job_id": job.job_id, "config_version": version}


if __name__ == "__main__":
    main()
