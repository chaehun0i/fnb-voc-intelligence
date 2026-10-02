"""명시한 로컬 테스트 주소에서 nginx 프록시와 수동 Incident 흐름을 검증합니다."""

import json
import os
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
    ) -> tuple[int, bytes, dict[str, str]]:
        headers = {"Accept": "application/json"}
        if request_id:
            headers["X-Request-ID"] = request_id
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
    ) -> Any:
        self.sequence += 1
        request_id = f"serviq-http-smoke-{self.sequence}"
        actual, raw, headers = self.fetch(
            method, f"{self.base_url}{path}", body, request_id
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
    workspace("execute", False)
    client.api(
        "POST",
        f"{path}/execute",
        {"expected_version": incident["version"]},
        status=409,
        error_code="DOMAIN_RULE_VIOLATION",
    )
    command("approve", "PENDING_APPROVAL")
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
    print(f"검증용 Incident: {identifier}")


def main() -> None:
    base_url = os.environ.get("SERVIQ_TEST_API_BASE_URL")
    if not base_url:
        raise SystemExit("로컬 테스트 스택의 SERVIQ_TEST_API_BASE_URL을 명시해 주세요.")
    client = SmokeClient(base_url)
    verify_frontend(client)
    verify_incident_flow(client)


if __name__ == "__main__":
    main()
