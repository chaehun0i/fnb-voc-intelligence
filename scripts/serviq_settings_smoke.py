"""명시한 테스트 DB에서 설정 버전·권한·멱등성·원자 저장을 검증합니다."""
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.domain.config.models import RuntimeConfig, config_document
from src.domain.config.resolution import ConfigResolver
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.jobs.job_dispatch import PostgresJobDispatcher
from src.infrastructure.jobs.outbox_worker import OutboxWorker
from src.infrastructure.migrations import migrate
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def verify(dsn):
    suffix = uuid4().hex
    tenant, other = "settings-"+suffix, "settings-other-"+suffix
    admin = Principal("settings-admin", tenant, frozenset({Role.HQ_ADMIN}))
    provider = LocalIdentityProvider({"admin": admin, "other": replace(admin, tenant_id=other),
        "auditor": replace(admin, principal_id="auditor", roles=frozenset({Role.AUDITOR})),
        "operator": replace(admin, principal_id="operator", roles=frozenset({Role.OPS_MANAGER}))}, environment="test")
    migrate(dsn)
    migrate(dsn)

    def new_app():
        return create_app(PostgresIncidentRepository(dsn), identity_provider=provider,
                          clock=lambda: datetime(2026, 10, 4, 9, tzinfo=UTC))

    http = TestClient(new_app())
    path = "/api/v1/settings/runtime"
    def request(method, endpoint="", body=None, *, token="admin", key=None, status=200, client=None):
        headers = {"Authorization": "Bearer "+token, "X-Request-ID": "day20-settings-smoke"}
        if method == "POST":
            headers["Idempotency-Key"] = key or str(uuid4())
        response = (client or http).request(method, path+endpoint, json=body, headers=headers)
        assert response.status_code == status, (endpoint, response.status_code, response.text)
        assert response.json().get("request_id", "day20-settings-smoke") == "day20-settings-smoke"
        return response.json()

    default = request("GET")
    assert default["config"]["version"] == 0 and default["sources"]["max_tool_calls"] == "PLATFORM_DEFAULT"
    first_body = {"config": config_document(RuntimeConfig()), "expected_version": 0, "reason": "초기 운영 설정"}
    first = request("POST", body=first_body, key="initial")
    assert first["config"]["version"] == 1 and first["runtime_status"] == "NOT_CONNECTED"
    assert request("POST", body=first_body, key="initial") == first
    second_body = {"config": config_document(RuntimeConfig(max_tool_calls=10)), "expected_version": 1, "reason": "도구 예산 축소"}
    second = request("POST", body=second_body, key="update")
    assert second["config"]["version"] == 2
    assert request("POST", body=second_body, key="update") == second
    assert request("GET", "/history?limit=1")["has_more"]
    history = request("GET", "/history")
    assert [r["version"] for r in history["revisions"]] == [2, 1]
    assert history["revisions"][0]["changes"] == [{"field": "max_tool_calls", "before": "20", "after": "10"}]
    assert history["revisions"][1]["rollback_changes"] == [{"field": "max_tool_calls", "before": "10", "after": "20"}]
    assert request("GET", token="other")["config"]["version"] == 0
    assert request("GET", "/history", token="other")["revisions"] == []
    request("POST", body=first_body, token="other", key="initial")
    request("POST", "/rollback", {"target_version": 2, "expected_version": 1, "reason": "타 조직 원본 접근"}, token="other", status=404)
    request("POST", body=second_body, token="auditor", status=403)
    request("POST", body=second_body, token="operator", status=403)
    assert not request("GET", token="auditor")["save_permission"]["allowed"]
    request("POST", body={**second_body, "reason": "다른 내용"}, key="update", status=409)
    assert request("POST", body=first_body, status=409)["error"]["code"] == "VERSION_CONFLICT"
    assert request("POST", body={**second_body, "expected_version": 2, "config": {**second_body["config"], "max_tool_calls": 100}}, status=422)["error"]["code"] == "CONFIG_VALIDATION_FAILED"
    request("POST", body={**second_body, "expected_version": 2, "config": {**second_body["config"], "auto_execute": True, "approval_policy_by_risk": {"LOW": False, "MEDIUM": True, "HIGH": False, "CRITICAL": True}}}, status=422)
    request("POST", body={**second_body, "expected_version": 2, "config": {**second_body["config"], "allowed_tools": ["execute_sql"]}}, status=422)
    # 과거 snapshot은 현재 상한으로 재검증합니다. 원본 row는 수정하지 않습니다.
    capped_app = new_app()
    capped_app.state.config_resolver = ConfigResolver(rules={"max_tool_calls": (1, 10, True)})
    request("POST", "/rollback", {"target_version": 1, "expected_version": 2, "reason": "상한 위반 복원"}, client=TestClient(capped_app), status=422)
    rollback_body = {"target_version": 1, "expected_version": 2, "reason": "초기 설정 복원"}
    third = request("POST", "/rollback", rollback_body, key="rollback")
    assert third["config"]["version"] == 3 and third["config"]["max_tool_calls"] == 20
    assert request("POST", "/rollback", rollback_body, key="rollback") == third
    assert request("POST", "/rollback", {**rollback_body, "reason": "다른 이유"}, key="rollback", status=409)["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    barrier = Barrier(2)
    def race(index):
        client = TestClient(new_app())
        barrier.wait()
        body = {**second_body, "expected_version": 3, "reason": f"동시 변경 {index}"}
        return client.post(path, headers={"Authorization": "Bearer admin", "Idempotency-Key": f"race-{index}"}, json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(race, [1, 2]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert next(r for r in responses if r.status_code == 409).json()["error"]["code"] == "VERSION_CONFLICT"
    duplicate_body = {**second_body, "expected_version": 4, "reason": "동일 변경 동시 재전송"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        duplicates = list(pool.map(lambda _: request("POST", body=duplicate_body, key="duplicate", client=TestClient(new_app())), [1, 2]))
    assert duplicates[0] == duplicates[1] and duplicates[0]["config"]["version"] == 5
    assert request("GET", client=TestClient(new_app()))["config"]["version"] == 5

    with psycopg.connect(dsn, autocommit=True) as connection:
        rows = connection.execute("SELECT config_version,config_json,parent_version,rollback_source FROM serviq_config_versions WHERE tenant_id=%s ORDER BY config_version", (tenant,)).fetchall()
        assert len(rows) == 5 and rows[0][1] == first_body["config"] and rows[1][1] == second_body["config"]
        assert rows[2][2:] == (2, 1)
        for verb in ("UPDATE serviq_config_versions SET reason='변경 금지'", "DELETE FROM serviq_config_versions"):
            try:
                with connection.transaction():
                    connection.execute(verb + " WHERE tenant_id=%s AND config_version=1", (tenant,))
            except psycopg.errors.RaiseException:
                pass
            else:
                raise AssertionError("과거 버전 수정·삭제가 금지되어야 합니다.")
        audits = connection.execute("SELECT document FROM serviq_audit WHERE tenant_id=%s", (tenant,)).fetchall()
        assert sum(a[0]["result"] == "SUCCESS" for a in audits) == 5
        assert sum(a[0]["result"] == "DENIED" for a in audits) == 2
        assert all(a[0]["resource_type"] == "runtime_config" and a[0]["tenant_id"] == tenant for a in audits)
        assert all("config" not in a[0] and "secret" not in a[0] for a in audits)
        events = connection.execute("SELECT payload,incident_id FROM serviq_outbox WHERE tenant_id=%s AND event_type='config.changed'", (tenant,)).fetchall()
        assert len(events) == 5 and all(row[1] is None and "config" not in row[0] for row in events)
        # Audit insert 실패 시 버전·이벤트·멱등성 claim도 함께 롤백해야 합니다.
        constraint = "settings_smoke_"+suffix
        connection.execute(sql.SQL("ALTER TABLE serviq_audit ADD CONSTRAINT {} CHECK (NOT (tenant_id={} AND document->>'result'='SUCCESS' AND (document->>'resulting_version')::int=6)) NOT VALID").format(sql.Identifier(constraint), sql.Literal(tenant)))
        try:
            unavailable = request("POST", body={**second_body, "expected_version": 5, "reason": "감사 실패 롤백"}, key="atomic", status=503)
            assert unavailable["error"]["code"] == "SETTINGS_UNAVAILABLE"
            assert "constraint" not in str(unavailable)
            assert connection.execute("SELECT count(*) FROM serviq_config_versions WHERE tenant_id=%s", (tenant,)).fetchone()[0] == 5
            assert connection.execute("SELECT count(*) FROM serviq_idempotency WHERE tenant_id=%s AND key='atomic'", (tenant,)).fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM serviq_outbox WHERE tenant_id=%s", (tenant,)).fetchone()[0] == 5
        finally:
            connection.execute(sql.SQL("ALTER TABLE serviq_audit DROP CONSTRAINT {}").format(sql.Identifier(constraint)))
        worker = OutboxWorker(connection, processor=PostgresJobDispatcher(connection, PostgresIncidentRepository(dsn)))
        for _ in range(1000):
            if not worker.run_once():
                break
        assert connection.execute("SELECT count(*) FROM serviq_outbox WHERE tenant_id=%s AND status='COMPLETED'", (tenant,)).fetchone()[0] == 5
        assert connection.execute("SELECT count(*) FROM serviq_jobs WHERE tenant_id=%s", (tenant,)).fetchone()[0] == 0
    print("[통과] Settings PostgreSQL version/history/diff/immutable/rollback/current-cap/tenant/RBAC")
    print("[통과] expected_version 동시 충돌·동시/재시작 멱등성·Audit/Outbox 원자 롤백·Config 이벤트 Worker 검증")


def main():
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("전용 테스트 DB의 SERVIQ_TEST_DATABASE_URL을 명시해 주세요.")
    verify(dsn)


if __name__ == "__main__":
    main()
