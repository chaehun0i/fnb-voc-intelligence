"""명시한 로컬 테스트 주소에서 nginx 프록시와 수동 Incident 흐름을 검증합니다."""

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from uuid import UUID, uuid4


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class SmokeClient:
    def __init__(self, base_url: str) -> None:
        parsed = urlsplit(base_url)
        check(
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and parsed.path.rstrip("/") == "/api/v1"
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment,
            "로컬 테스트 스택의 http://주소:포트/api/v1만 지정해 주세요.",
        )
        self.base_url = base_url.rstrip("/")
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.opener = build_opener(ProxyHandler({}))
        self.sequence = 0

    def fetch(
        self,
        method: str,
        url: str,
        body: dict | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        headers = {"Accept": "application/json"}
        if request_id:
            headers["X-Request-ID"] = request_id
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=10) as response:
                return response.status, response.read(), dict(response.headers.items())
        except HTTPError as error:
            with error:
                return error.code, error.read(), dict(error.headers.items())
        except URLError:
            raise AssertionError(
                "로컬 Compose 테스트 주소에 연결하지 못했습니다."
            ) from None

    def api(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        status: int = 200,
        error_code: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        self.sequence += 1
        request_id = f"serviq-http-smoke-{self.sequence}"
        actual, raw, headers = self.fetch(
            method, f"{self.base_url}{path}", body, request_id,
            (idempotency_key or str(uuid4())) if method == "POST" else None,
        )
        check(actual == status, f"{method} {path}: HTTP {status} 예상, {actual} 응답")
        check(
            next(
                (
                    value
                    for key, value in headers.items()
                    if key.lower() == "x-request-id"
                ),
                None,
            )
            == request_id,
            "nginx 프록시를 통한 요청 식별자 전달이 일치하지 않습니다.",
        )
        try:
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AssertionError("API가 읽을 수 있는 JSON을 반환해야 합니다.") from None
        if error_code:
            check(isinstance(data, dict), "오류 응답은 객체여야 합니다.")
            check(
                data.get("error", {}).get("code") == error_code,
                "안정적인 오류 코드가 일치하지 않습니다.",
            )
            check(
                data.get("request_id") == request_id,
                "오류 본문과 응답 헤더의 요청 식별자가 일치해야 합니다.",
            )
            check(
                isinstance(data["error"].get("message"), str)
                and bool(data["error"]["message"]),
                "오류 응답에 사용자 안내가 필요합니다.",
            )
        return data


def verify_frontend(client: SmokeClient) -> None:
    status, body, _ = client.fetch("GET", f"{client.origin}/healthz")
    check(
        status == 200 and body.strip() == b"ok",
        "nginx healthz 응답이 올바르지 않습니다.",
    )
    status, body, headers = client.fetch("GET", f"{client.origin}/")
    content_type = next(
        (value for key, value in headers.items() if key.lower() == "content-type"), ""
    )
    check(
        status == 200 and "text/html" in content_type and b"<html" in body.lower(),
        "프론트엔드 정적 화면을 제공하지 못했습니다.",
    )
    check(
        client.api("GET", "/health") == {"status": "ok"},
        "nginx API 프록시 health가 실패했습니다.",
    )
    print("[통과] nginx 정적 화면·healthz·API 프록시·요청 식별자")


def verify_incident_flow(client: SmokeClient) -> None:
    baseline_dashboard = client.api("GET", "/dashboard?window=7d")
    check(baseline_dashboard["window"] == "7d" and baseline_dashboard["timezone"] == "UTC", "Dashboard 기간·날짜 기준이 필요합니다.")
    client.api("GET", "/dashboard?window=all", status=422, error_code="VALIDATION_ERROR")
    suffix = uuid4().hex
    store = f"CI 검증-{suffix[:12]}"
    client.api(
        "POST",
        "/incidents",
        {"title": "", "severity": "HIGH", "store": store, "owner": "CI 검증"},
        status=422,
        error_code="VALIDATION_ERROR",
    )
    client.api("GET", f"/incidents/{uuid4()}", status=404, error_code="NOT_FOUND")
    incident = client.api(
        "POST",
        "/incidents",
        {
            "title": "CI 프록시 수동 운영 흐름 검증",
            "severity": "HIGH",
            "store": store,
            "owner": "CI 검증",
            "priority": "P1",
        },
        status=201,
    )
    check(isinstance(incident, dict), "생성 응답은 Incident 객체여야 합니다.")
    identifier = incident["id"]
    created_dashboard = client.api("GET", "/dashboard?window=7d")
    check(created_dashboard["kpis"]["open_incidents"] == baseline_dashboard["kpis"]["open_incidents"] + 1, "생성 후 실제 Dashboard 열린 사건 수가 증가해야 합니다.")
    UUID(identifier)
    path = f"/incidents/{quote(identifier, safe='')}"
    check(
        incident["status"] == "DETECTED" and incident["version"] == 1,
        "생성된 최초 상태와 버전이 일치하지 않습니다.",
    )
    check(
        client.api("GET", path) == incident,
        "생성한 Incident 상세가 저장 결과와 다릅니다.",
    )

    def workspace(command: str, allowed: bool) -> None:
        permission = client.api("GET", f"{path}/workspace")["commands"][command]
        check(
            permission["allowed"] is allowed
            and isinstance(permission["reason"], str)
            and bool(permission["reason"]),
            f"{command} Permission의 허용 여부와 이유가 필요합니다.",
        )

    def command(name: str, next_status: str, body: dict | None = None) -> None:
        nonlocal incident
        previous_version = incident["version"]
        incident = client.api(
            "POST",
            f"{path}/{name}",
            {"expected_version": previous_version, **(body or {})},
        )
        check(
            incident["id"] == identifier and incident["status"] == next_status,
            f"{name} 명령 결과의 Incident 또는 상태가 다릅니다.",
        )
        check(
            incident["version"] == previous_version + 1,
            f"{name} 명령 후 저장 버전이 증가해야 합니다.",
        )

    workspace("triage", True)
    client.api("PATCH", path, {"status": "CLOSED"}, status=405, error_code="HTTP_ERROR")
    client.api(
        "POST",
        f"{path}/close",
        {"expected_version": 1},
        status=409,
        error_code="DOMAIN_RULE_VIOLATION",
    )
    client.api(
        "POST",
        f"{path}/triage",
        {"expected_version": 1, "status": "CLOSED"},
        status=422,
        error_code="VALIDATION_ERROR",
    )
    check(
        client.api("GET", path) == incident,
        "거부된 요청이 최초 Incident를 변경했습니다.",
    )
    command("triage", "TRIAGED", {"severity": "HIGH"})
    workspace("triage", False)
    workspace("investigate", True)
    client.api(
        "POST",
        f"{path}/investigate",
        {"expected_version": 1},
        status=409,
        error_code="CONFLICT",
    )
    command("investigate", "INVESTIGATING")
    evidence_id = f"ci-evidence-{suffix}"
    command(
        "evidence",
        "INVESTIGATING",
        {
            "evidence": {
                "id": evidence_id,
                "source": "CI 온도 기록",
                "type": "MANUAL_RECORD",
                "summary": "냉장 온도 기록을 확인했습니다.",
                "confidence": 0.98,
            }
        },
    )
    command(
        "rca",
        "RCA_READY",
        {
            "candidates": [
                {
                    "id": f"ci-rca-{suffix}",
                    "summary": "냉각 장치 점검이 필요합니다.",
                    "confidence": 0.85,
                    "supporting_evidence_ids": [evidence_id],
                    "counter_evidence_ids": [],
                }
            ]
        },
    )
    command(
        "actions",
        "ACTION_PROPOSED",
        {
            "actions": [
                {
                    "id": f"ci-action-{suffix}",
                    "summary": "담당자가 냉각 장치를 점검합니다.",
                    "risk_level": "HIGH",
                    "expected_effect": "보관 온도를 회복합니다.",
                    "verification_criteria": "정상 온도 유지 기록을 확인합니다.",
                }
            ]
        },
    )
    command("request-approval", "PENDING_APPROVAL")
    check(client.api("GET", "/dashboard?window=7d")["kpis"]["pending_approvals"] == baseline_dashboard["kpis"]["pending_approvals"] + 1, "실제 승인 요청이 Dashboard 대기 수에 반영되어야 합니다.")
    workspace("execute", False)
    client.api(
        "POST",
        f"{path}/execute",
        {"expected_version": incident["version"]},
        status=409,
        error_code="DOMAIN_RULE_VIOLATION",
    )
    review = next(item for item in client.api("GET", "/reviews") if item["incident_id"] == identifier)
    review_path = f"/reviews/{review['id']}"
    check(client.api("GET", review_path)["approval"]["actions"]["approve"]["allowed"], "서버의 승인 권한이 필요합니다.")
    approval_body = {"reason": "CI 검토자가 증거와 조치안을 확인했습니다.", "expected_version": review["version"]}
    approval_key = f"http-approval-{suffix}"
    incident = client.api("POST", review_path+"/approve", approval_body, idempotency_key=approval_key)
    check(client.api("POST", review_path+"/approve", approval_body, idempotency_key=approval_key) == incident, "동일 승인 재전송은 이전 결과를 반환해야 합니다.")
    client.api("POST", review_path+"/approve", {**approval_body, "reason": "다른 사유"}, idempotency_key=approval_key, status=409, error_code="IDEMPOTENCY_CONFLICT")
    check(client.api("GET", review_path)["approval"]["status"] == "APPROVED", "Review 원본의 승인 결과가 필요합니다.")
    check(client.api("GET", "/dashboard?window=7d")["kpis"]["pending_approvals"] == baseline_dashboard["kpis"]["pending_approvals"], "승인 결정 후 Dashboard 대기 수가 복구되어야 합니다.")
    check(incident["approved"] is True, "사람 승인 기록이 반영되어야 합니다.")
    workspace("execute", True)
    command("execute", "VERIFYING")
    client.api(
        "POST",
        f"{path}/close",
        {"expected_version": incident["version"]},
        status=409,
        error_code="DOMAIN_RULE_VIOLATION",
    )
    command(
        "verify",
        "RESOLVED",
        {"result": "PASS", "summary": "담당자가 정상 온도 유지 기록을 확인했습니다."},
    )
    check(
        incident["verification"]["result"] == "PASS",
        "검증 PASS 결과가 저장되어야 합니다.",
    )
    command("close", "CLOSED")
    check(
        client.api("GET", path) == incident,
        "종결한 Incident가 조회 결과에 유지되어야 합니다.",
    )
    query = urlencode({"status": "CLOSED", "severity": "HIGH", "store": store})
    filtered = client.api("GET", f"/incidents?{query}")
    check(
        [item["id"] for item in filtered] == [identifier],
        "프록시 목록 필터가 해당 Incident를 반환해야 합니다.",
    )
    closed_workspace = client.api("GET", f"{path}/workspace")
    check(
        all(
            permission["allowed"] is False
            for permission in closed_workspace["commands"].values()
        ),
        "종결한 Incident의 일반 명령은 비활성 상태여야 합니다.",
    )
    print("[통과] 실제 HTTP 생성→분류→조사→증거→RCA→조치→승인→실행 기록→검증→종결")
    print("[통과] Workspace Permission·목록 필터·404/422/409·버전 충돌·임의 PATCH 거부")
    print("[통과] 실제 Review 조회·승인·멱등 재전송·내용 충돌")
    jobs = []
    for _ in range(20):
        jobs = client.api("GET", "/jobs?" + urlencode({"incident_id": identifier}))
        if jobs and jobs[0]["status"] == "COMPLETED":
            break
        time.sleep(0.5)
    check(len(jobs) == 1 and jobs[0]["status"] == "COMPLETED", "Outbox dispatch와 독립 Job Worker가 작업을 완료해야 합니다.")
    job = jobs[0]
    check(client.api("GET", "/jobs/" + job["id"]) == job, "실제 Queue 상세 원본이 일치해야 합니다.")
    check(job["correlation_id"] == identifier and "payload_ref" not in job, "상관관계 보존과 민감한 원본 미노출이 필요합니다.")
    check(not job["actions"]["retry"]["allowed"] and not job["actions"]["cancel"]["allowed"], "완료 작업의 재시도와 취소는 서버에서 거부해야 합니다.")
    client.api("POST", "/jobs/" + job["id"] + "/retry", {"reason": "완료 작업 보호 확인", "expected_version": job["version"]}, status=409, error_code="JOB_TRANSITION_NOT_ALLOWED")
    print("[통과] nginx→Queue list/detail→Outbox dispatch→독립 Worker 완료·상관관계·terminal 보호")
    dashboard = client.api("GET", "/dashboard?window=7d")
    check(dashboard["kpis"]["open_incidents"] == baseline_dashboard["kpis"]["open_incidents"], "종결 후 Dashboard 열린 사건 수가 복구되어야 합니다.")
    check(dashboard["integration_health"]["status"] == "NOT_IMPLEMENTED", "연동 Mock을 실제 Dashboard로 합치면 안 됩니다.")
    check(len(dashboard["incident_trend"]) == 7 and isinstance(dashboard["as_of"], str), "Dashboard의 기준 시각과 7개 날짜 버킷이 필요합니다.")
    check(sum(x["count"] for x in dashboard["root_cause_distribution"]) == sum(x["count"] for x in baseline_dashboard["root_cause_distribution"]) + 1, "실제 RCA 후보가 Dashboard에 반영되어야 합니다.")
    check(next(x["count"] for x in dashboard["capa_status"] if x["status"] == "EXECUTED") == next(x["count"] for x in baseline_dashboard["capa_status"] if x["status"] == "EXECUTED") + 1, "실제 실행된 CAPA가 Dashboard에 반영되어야 합니다.")
    print("[통과] nginx Dashboard 단일 Query·기준 시각·기간 검증·Incident/RCA/CAPA 변화·Mock 미혼합")
    print(f"검증용 Incident: {identifier}")


def main() -> None:
    base_url = os.environ.get("SERVIQ_TEST_API_BASE_URL")
    if not base_url:
        raise SystemExit("로컬 테스트 스택의 SERVIQ_TEST_API_BASE_URL을 명시해 주세요.")
    client = SmokeClient(base_url)
    verify_frontend(client)
    verify_incident_flow(client)
    verify_settings_flow(client)
    verify_jev_flow(client)
    fixture = os.getenv("SERVIQ_CAPA_HTTP_FIXTURE")
    if fixture:
        verify_capa_http(client, json.loads(fixture))


def verify_capa_http(client, fixture):
    """검증 전용 Job은 Application에서 등록하고 nginx에서는 실제 Review만 사용합니다."""
    identifier = str(UUID(fixture["incident_id"]))
    UUID(fixture["job_id"])
    check(isinstance(fixture["config_version"], int) and fixture["config_version"] > 0, "고정 Config 버전이 필요합니다.")
    path = f"/incidents/{identifier}/agent-runs"
    run = None
    for _ in range(30):
        runs = client.api("GET", path)["runs"]
        if runs and runs[0]["status"] in {"WAITING_APPROVAL", "FAILED", "COMPLETED"}:
            run = runs[0]
            break
        time.sleep(.5)
    check(run is not None and run["status"] == "WAITING_APPROVAL", "실제 Worker가 Approval interrupt에 도달해야 합니다.")
    detail_path = path+"/"+run["agent_run_id"]
    detail = client.api("GET", detail_path)
    check(detail["config_version"] == fixture["config_version"] and len(detail["capa_proposals"]) == 1, "실제 CAPA와 Config lineage가 필요합니다.")
    check(detail["sufficiency"]["status"] == "SUFFICIENT" and detail["approval"]["phase"] == "WAITING_APPROVAL", "충분한 근거와 실제 승인 대기가 필요합니다.")
    review_path = "/reviews/"+detail["approval"]["approval_id"]
    review = client.api("GET", review_path)
    check(review["approval"]["actions"]["approve"]["allowed"], "서버가 계산한 실제 Review 권한이 필요합니다.")
    body = {"expected_version": review["approval"]["version"], "reason": "HTTP 검토자가 근거와 검증 기준을 확인했습니다."}
    key = "http-capa-"+identifier
    approved = client.api("POST", review_path+"/approve", body, idempotency_key=key)
    check(client.api("POST", review_path+"/approve", body, idempotency_key=key) == approved, "동일 결정은 resume Job을 중복 생성하면 안 됩니다.")
    for _ in range(30):
        detail = client.api("GET", detail_path)
        if detail["status"] in {"COMPLETED", "FAILED"}:
            break
        time.sleep(.5)
    check(detail["status"] == "COMPLETED" and detail["approval"]["phase"] == "READY_TO_EXECUTE", "실제 resume Worker가 승인된 분기를 복원해야 합니다.")
    item = client.api("GET", "/incidents/"+identifier)
    check(item["status"] == "PENDING_APPROVAL" and item["approved"] and all(a["status"] != "EXECUTED" for a in item["corrective_actions"]), "승인은 실행 완료가 아닙니다.")
    check(not any(v in json.dumps(detail) for v in ("SYNTHETIC-RAW-SENTINEL", "raw_prompt", "raw_response", "delegated_roles")), "Trace에 원문이나 권한 위임 정보가 노출되면 안 됩니다.")
    jobs = client.api("GET", "/jobs?"+urlencode({"incident_id": identifier}))
    check(len([j for j in jobs if j["type"] == "incident.history_resume"]) == 1, "승인 재전송으로 resume Job이 중복되면 안 됩니다.")
    print("[통과] nginx→실제 CAPA/승인 Trace→Review 승인→persistent resume Job→checkpoint 재개·실행 미기록")


def verify_settings_flow(client):
    path = "/settings/runtime"
    current = client.api("GET", path)
    version = current["config"]["version"]
    config = {key: value for key, value in current["config"].items() if key != "version"}
    initial = client.api("POST", path, {"config": config, "expected_version": version, "reason": "HTTP 초기 설정 기록"})
    target = initial["config"]["version"]
    changed = {**config, "max_tool_calls": 10 if config["max_tool_calls"] != 10 else 15}
    key = str(uuid4())
    body = {"config": changed, "expected_version": target, "reason": "HTTP 실행 예산 검증"}
    saved = client.api("POST", path, body, idempotency_key=key)
    check(client.api("POST", path, body, idempotency_key=key) == saved, "설정 재전송은 이전 버전 결과여야 합니다.")
    client.api("POST", path, {**body, "reason": "다른 내용"}, idempotency_key=key, status=409, error_code="IDEMPOTENCY_CONFLICT")
    client.api("POST", path, body, status=409, error_code="VERSION_CONFLICT")
    client.api("POST", path, {**body, "expected_version": target+1, "config": {**changed, "max_tool_calls": 100}}, status=422, error_code="CONFIG_VALIDATION_FAILED")
    history = client.api("GET", path+"/history")
    check(history["revisions"][0]["version"] == target+1 and history["revisions"][0]["changes"], "설정 변경 이력과 diff가 필요합니다.")
    rollback_key = str(uuid4())
    rollback_body = {"target_version": target, "expected_version": target+1, "reason": "HTTP 원래 예산 복원"}
    restored = client.api("POST", path+"/rollback", rollback_body, idempotency_key=rollback_key)
    check(client.api("POST", path+"/rollback", rollback_body, idempotency_key=rollback_key) == restored, "복원 재전송이 버전을 중복 생성하면 안 됩니다.")
    check(restored["config"]["version"] == target+2 and restored["effective"] == config, "복원은 원래 값으로 새 버전을 만들어야 합니다.")
    check(restored["runtime_status"] == "NOT_CONNECTED", "설정 저장이 Runtime 활성화처럼 표시되면 안 됩니다.")
    check(client.api("GET", path)["config"]["version"] == target+2, "현재 버전은 실제 DB 결과여야 합니다.")
    print("[통과] nginx Settings current/update/history/diff/rollback·버전 충돌·상한·멱등성·Runtime 미연결")


def verify_jev_flow(client):
    current = client.api("GET", "/settings/runtime")
    config = {key: value for key, value in current["config"].items() if key != "version"}
    enabled = client.api("POST", "/settings/runtime", {"config": {**config, "jev_enabled": True}, "expected_version": current["config"]["version"], "reason": "HTTP Shadow 판단 검증"})
    incident = client.api("POST", "/incidents", {"title": "Shadow HTTP 검증", "severity": "MEDIUM", "store": "검증 매장", "owner": "검증 담당"}, status=201)
    path = "/incidents/"+incident["id"]+"/decisions"
    latest = None
    for _ in range(20):
        latest = client.api("GET", path+"/latest")
        if latest is not None:
            break
        time.sleep(.5)
    check(latest is not None and latest["mode"] == "SHADOW", "실제 Worker가 Shadow 판단을 저장해야 합니다.")
    check(latest["config_version"] == enabled["config"]["version"] and not latest["requires_llm"], "판단은 실제 Config 버전을 보존하고 LLM을 호출하지 않아야 합니다.")
    check(latest["route"] == "MANUAL_REVIEW" and not latest["investigation_agents"], "데이터가 없는 작업에서 모든 Agent를 후보로 실행하면 안 됩니다.")
    check(client.api("GET", "/incidents/"+incident["id"]) == incident, "Shadow 판단은 Incident 업무 상태를 변경하면 안 됩니다.")
    history = client.api("GET", path)
    check(len(history["decisions"]) == 1 and "input_digest" not in latest and "tenant_id" not in latest, "읽기 전용 안전 계약과 판단 이력이 필요합니다.")
    print("[통과] nginx→실제 Job Worker→Jev Shadow 저장→history/latest·Config 버전·업무 상태 보존")
    calls_path = "/incidents/"+incident["id"]+"/llm-calls"
    check(client.api("GET", calls_path)["calls"] == [], "Jev Shadow는 외부 LLM 호출을 생성하지 않아야 합니다.")
    client.api("GET", calls_path+"?limit=101", status=422, error_code="VALIDATION_ERROR")
    print("[통과] nginx LLM 사용 기록 읽기 경계·조회 상한·Shadow 자동 AI 호출 없음")
    runs_path = "/incidents/"+incident["id"]+"/agent-runs"
    check(client.api("GET", runs_path)["runs"] == [], "Shadow는 자동 AgentRun을 만들면 안 됩니다.")
    client.api("GET", runs_path+"?limit=101", status=422, error_code="VALIDATION_ERROR")
    client.api("POST", runs_path, {}, status=405, error_code="HTTP_ERROR")
    print("[통과] nginx AgentRun 조회·상한·공개 실행 POST 금지·Shadow 자동 조사 없음")


if __name__ == "__main__":
    main()
