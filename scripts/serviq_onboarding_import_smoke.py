"""격리 DB에서 실제 입력 API→Jev→Worker→Checkpoint→근거를 검증합니다."""
import json
import os
from contextlib import contextmanager
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from src.ai.workflow.runtime import HistoryProcessor, postgres_checkpoint
from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.data.database import initialize_schema
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.history_search import PostgresHistorySearch
from src.infrastructure.investigation_source import PostgresInvestigationSource
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.migrations import migrate
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def verify(dsn):
    migrate(dsn)
    with psycopg.connect(dsn) as connection:
        initialize_schema(connection)
    tenant = "intake-"+uuid4().hex
    principal = Principal("intake-admin", tenant, frozenset({Role.HQ_ADMIN}))
    identity = LocalIdentityProvider({"admin": principal,
        "other": Principal("other", tenant+"-other", frozenset({Role.HQ_ADMIN}))})
    app = create_app(PostgresIncidentRepository(dsn), identity_provider=identity)
    client = TestClient(app)
    h = {"Authorization": "Bearer admin", "Idempotency-Key": "intake-smoke"}
    assert client.get("/api/v1/data/onboarding", headers=h).json()["first_run"]
    assert client.post("/api/v1/data/stores", headers=h, json={"store": "체험 매장"}).status_code == 200
    sample = client.post("/api/v1/data/sample", headers=h, json={"store": "체험 매장", "confirmed": True})
    assert sample.status_code == 200, sample.text
    receipt = sample.json()
    assert client.post("/api/v1/data/sample", headers=h, json={"store": "체험 매장", "confirmed": True}).json() == receipt
    assert client.post("/api/v1/data/initialize-runtime", headers=h, json={"confirmed": True}).status_code == 200
    path = "/api/v1/data/imports/"+receipt["import_id"]+"/analysis"
    response = client.post(path, headers=h, json={"topic": "품질"})
    assert response.status_code == 200, response.text
    analysis = response.json()
    assert client.post(path, headers={**h, "Authorization": "Bearer other"}, json={"topic": "품질"}).status_code == 404
    p = app.state.access_persistence
    @contextmanager
    def checkpoint():
        with postgres_checkpoint(dsn) as saver:
            yield saver
    processor = HistoryProcessor(p, PostgresHistorySearch(dsn), checkpoint, dsn=dsn,
        source=PostgresInvestigationSource(dsn))
    with psycopg.connect(dsn, autocommit=True) as connection:
        worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor), tenant_id=tenant)
        for _ in range(12):
            if not worker.run_once():
                break
    # New repository objects verify persistence independently of the HTTP request/process.
    restarted = create_app(PostgresIncidentRepository(dsn), identity_provider=identity)
    with restarted.state.access_persistence.transaction(tenant) as uow:
        runs = uow.agent_runs.history(analysis["incident_id"])
        assert len(runs) == 1
        run = runs[0]
        assert run.state.normalized_evidence, run.model_dump_json()
        assert run.state.findings and run.manifest
        assert not uow.configs.current().config.hosted_ai_allowed
        assert len(uow.intake.list("SOURCE")) == 4
        encoded = run.model_dump_json()
        assert "메뉴 제공 상태 확인" not in encoded
    assert client.post(path, headers=h, json={"topic": "품질"}).json()["job_id"] == analysis["job_id"]
    status = TestClient(restarted).get("/api/v1/data/onboarding", headers=h).json()
    assert status["checklist"]["results"] and not status["first_run"]
    # Canonical file input remains separate from its temporary preview.
    assert client.post("/api/v1/data/stores", headers={**h, "Idempotency-Key": "file-store"}, json={"store": "파일 매장"}).status_code == 200
    csv = "매장명,자료ID,발생일시,VOC 내용,평점\n파일 매장,file-1,2026-10-07,품질 점검 필요,2\n"
    preview = client.post("/api/v1/data/preview", headers=h, data={"store": "파일 매장", "kind": "VOC"},
        files={"file": ("voc.csv", csv.encode(), "text/csv")}).json()
    assert preview["valid"]
    with p.transaction(tenant) as uow:
        assert len(uow.intake.list("SOURCE")) == 4
    confirmed = client.post("/api/v1/data/imports/"+preview["preview_id"]+"/confirm", headers=h,
        json={"digest": preview["digest"], "confirmed": True})
    assert confirmed.status_code == 200, confirmed.text
    with p.transaction(tenant) as uow:
        assert len(uow.intake.list("SOURCE")) == 5 and not uow.intake.list("PREVIEW")
    print(json.dumps({"onboarding": "PASS", "import": "PASS", "worker_checkpoint": "PASS",
        "evidence_count": len(run.state.normalized_evidence), "provider_calls": 0, "external_writes": 0}))


if __name__ == "__main__":
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("격리된 SERVIQ_TEST_DATABASE_URL이 필요합니다.")
    verify(dsn)
