"""전용 PostgreSQL에서 Day 17의 실행 안전 계약을 실제로 검증합니다."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.migrations import migrate
from src.infrastructure.outbox.worker import OutboxWorker
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def verify(dsn):
    suffix = uuid4().hex
    tenant, other = f"security-{suffix}", f"security-other-{suffix}"
    provider = LocalIdentityProvider({
        "test-operator": Principal("operator", tenant, frozenset({Role.HQ_ADMIN})),
        "test-reviewer": Principal("reviewer", tenant, frozenset({Role.REVIEWER})),
        "test-reader": Principal("reader", tenant, frozenset({Role.AUDITOR})),
        "test-other": Principal("operator", other, frozenset({Role.HQ_ADMIN})),
    }, environment="test")
    migrate(dsn)
    migrate(dsn)

    def client():
        return TestClient(create_app(PostgresIncidentRepository(dsn), identity_provider=provider,
                                    clock=lambda: datetime(2026, 10, 3, 9, tzinfo=UTC)))

    http = client()

    def request(method, path, body=None, token="test-operator", key=None, expected=200):
        headers = {"Authorization": f"Bearer {token}", "X-Request-ID": "day17-security-smoke"}
        if method == "POST":
            headers["Idempotency-Key"] = key or str(uuid4())
        response = http.request(method, "/api/v1"+path, headers=headers, json=body)
        assert response.status_code == expected, (path, response.status_code, response.text)
        return response.json()

    def pending(title):
        item = request("POST", "/incidents", {"title": title, "severity": "HIGH", "store": "검증 매장", "owner": "검증 담당"}, expected=201)
        path = "/incidents/"+item["id"]
        commands = [
            ("triage", {}), ("investigate", {}),
            ("evidence", {"evidence": {"id": "e1", "source": "기록", "type": "MANUAL_RECORD", "summary": "온도 확인", "confidence": 0.9}}),
            ("rca", {"candidates": [{"id": "r1", "summary": "냉각기", "confidence": 0.8, "supporting_evidence_ids": ["e1"]}]}),
            ("actions", {"actions": [{"id": "a1", "summary": "점검", "risk_level": "HIGH", "expected_effect": "안정", "verification_criteria": "기준 유지"}]}),
            ("request-approval", {}),
        ]
        for command, body in commands:
            item = request("POST", path+"/"+command, {"expected_version": item["version"], **body})
        approval = next(a for a in request("GET", "/reviews") if a["incident_id"] == item["id"])
        return item, approval

    with psycopg.connect(dsn, autocommit=True) as connection:
        item, approval = pending("승인 검증")
        path = "/reviews/"+approval["id"]
        assert request("GET", path)["detail"]["proposed_action"] == "점검"
        assert request("GET", path, token="test-reader")["approval"]["actions"]["approve"]["allowed"] is False
        assert request("GET", "/reviews", token="test-other") == []
        request("GET", path, token="test-other", expected=404)
        request("GET", "/incidents/"+item["id"], token="test-other", expected=404)
        body = {"reason": "증거와 조치 확인", "expected_version": approval["version"]}
        request("POST", path+"/approve", body, "test-reader", expected=403)
        request("POST", path+"/reject", body, "test-reader", expected=403)
        request("POST", path+"/approve", body, "test-other", expected=404)

        constraint = "security_audit_"+suffix
        connection.execute(sql.SQL("ALTER TABLE serviq_audit ADD CONSTRAINT {} CHECK (document->>'resource_id' <> {} OR document->>'result' <> 'SUCCESS')").format(sql.Identifier(constraint), sql.Literal(approval["id"])))
        before = connection.execute("SELECT count(*) FROM serviq_outbox WHERE incident_id=%s", (item["id"],)).fetchone()[0]
        try:
            try:
                request("POST", path+"/approve", body, "test-reviewer", "atomic-failure")
            except psycopg.errors.CheckViolation:
                pass
            else:
                raise AssertionError("감사 저장 실패가 업무를 롤백해야 합니다.")
            assert request("GET", path)["approval"]["status"] == "PENDING"
            assert request("GET", "/incidents/"+item["id"])["version"] == item["version"]
            assert connection.execute("SELECT count(*) FROM serviq_outbox WHERE incident_id=%s", (item["id"],)).fetchone()[0] == before
            assert connection.execute("SELECT count(*) FROM serviq_idempotency WHERE tenant_id=%s AND key='atomic-failure'", (tenant,)).fetchone()[0] == 0
        finally:
            connection.execute(sql.SQL("ALTER TABLE serviq_audit DROP CONSTRAINT {}").format(sql.Identifier(constraint)))

        first = request("POST", path+"/approve", body, "test-reviewer", "approve-once")
        http = client()  # 프로세스 내 객체를 교체해도 완료 결과는 DB에서 복원합니다.
        assert request("POST", path+"/approve", body, "test-reviewer", "approve-once") == first
        conflict = request("POST", path+"/approve", {**body, "reason": "다른 내용"}, "test-reviewer", "approve-once", expected=409)
        assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        request("POST", path+"/reject", body, "test-reviewer", "already-decided", expected=409)
        record = connection.execute("SELECT document FROM serviq_audit WHERE tenant_id=%s AND document->>'resource_id'=%s AND document->>'result'='SUCCESS'", (tenant, approval["id"])).fetchall()
        assert len(record) == 1
        assert record[0][0]["principal_id"] == "reviewer"
        assert record[0][0]["resource_type"] == "approval"
        assert record[0][0]["request_id"] == "day17-security-smoke"
        assert "test-reviewer" not in json.dumps(record)
        assert connection.execute("SELECT count(*) FROM serviq_outbox WHERE incident_id=%s", (item["id"],)).fetchone()[0] == before
        assert request("GET", path)["approval"]["status"] == "APPROVED"

        rejected, reject_approval = pending("반려 검증")
        reject_path = "/reviews/"+reject_approval["id"]+"/reject"
        rejected_result = request("POST", reject_path, {"reason": "근거 보완 필요", "expected_version": 1}, "test-reviewer", "reject-once")
        assert request("POST", reject_path, {"reason": "근거 보완 필요", "expected_version": 1}, "test-reviewer", "reject-once") == rejected_result
        assert request("GET", "/reviews/"+reject_approval["id"])["approval"]["status"] == "REJECTED"
        assert rejected_result["id"] == rejected["id"]

        create_body = {"title": "동시 요청", "severity": "HIGH", "store": "검증 매장", "owner": "담당"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: request("POST", "/incidents", create_body, key="race-once", expected=201), range(2)))
        assert results[0] == results[1]
        assert connection.execute("SELECT count(*) FROM serviq_audit WHERE tenant_id=%s AND document->>'resource_id'=%s", (tenant, results[0]["id"])).fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM serviq_outbox WHERE incident_id=%s", (results[0]["id"],)).fetchone()[0] == 1
        other_result = request("POST", "/incidents", create_body, "test-other", "race-once", expected=201)
        assert other_result["id"] != results[0]["id"]
        request("GET", "/incidents/"+other_result["id"], expected=404)
        assert connection.execute("SELECT count(*) FROM serviq_idempotency WHERE key='race-once' AND tenant_id=ANY(%s)", ([tenant, other],)).fetchone()[0] == 2
        try:
            connection.execute("UPDATE serviq_audit SET document=document WHERE tenant_id=%s", (tenant,))
        except psycopg.errors.RaiseException:
            pass
        else:
            raise AssertionError("감사 기록은 변경할 수 없어야 합니다.")

    with psycopg.connect(dsn, autocommit=True) as connection:
        worker = OutboxWorker(connection)
        for _ in range(100):
            if not worker.run_once():
                break
    print("[통과] PostgreSQL Tenant/RBAC·Approval·Audit·동시/재시작 Idempotency·원자적 롤백·Review 승인/반려")


def main():
    dsn = os.getenv("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("전용 테스트 DB의 SERVIQ_TEST_DATABASE_URL을 설정해 주세요.")
    verify(dsn)


if __name__ == "__main__":
    main()
