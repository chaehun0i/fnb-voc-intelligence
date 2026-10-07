"""HTTP smoke의 명시적 로컬 실행 조건을 외부 요청 없이 검증합니다."""

import json
import runpy
from pathlib import Path
from urllib.request import OpenerDirector

import pytest


@pytest.fixture(scope="module")
def smoke_script():
    script = Path(__file__).resolve().parents[2] / "scripts" / "serviq_http_smoke.py"
    return runpy.run_path(str(script))


@pytest.fixture(autouse=True)
def reject_network_requests(monkeypatch):
    def reject_request(*_args, **_kwargs):
        pytest.fail("주소 검증 단위 테스트에서는 HTTP 요청을 실행할 수 없습니다.")

    monkeypatch.setattr(OpenerDirector, "open", reject_request)


@pytest.mark.parametrize(
    "address",
    [
        "http://127.0.0.1:18080/api/v1",
        "http://localhost:18080/api/v1/",
        "http://[::1]:18080/api/v1",
    ],
)
def test_http_smoke_accepts_only_explicit_loopback_api_address(smoke_script, address):
    client = smoke_script["SmokeClient"](address)
    assert client.base_url == address.rstrip("/")
    assert client.sequence == 0


@pytest.mark.parametrize(
    "address",
    [
        "http://example.com/api/v1",
        "http://localhost.example.com/api/v1",
        "https://127.0.0.1:18080/api/v1",
        "http://test:test-password@127.0.0.1:18080/api/v1",
        "http://127.0.0.1:18080/api/v1?mode=prod",
        "http://127.0.0.1:18080/api/v1#fragment",
        "http://127.0.0.1:18080/",
        "file:///tmp/serviq",
    ],
)
def test_http_smoke_rejects_external_or_non_api_address(smoke_script, address):
    with pytest.raises(AssertionError, match="로컬 테스트 스택"):
        smoke_script["SmokeClient"](address)


def test_http_smoke_requires_explicit_environment_before_any_request(
    smoke_script, monkeypatch
):
    monkeypatch.delenv("SERVIQ_TEST_API_BASE_URL", raising=False)
    with pytest.raises(SystemExit, match="SERVIQ_TEST_API_BASE_URL"):
        smoke_script["main"]()


def test_verification_http_mode_preserves_preceding_full_regression(smoke_script, monkeypatch):
    calls = []
    namespace = smoke_script["main"].__globals__
    fixture = {"incident_id": "fixture", "outcome": "PASS"}
    monkeypatch.setenv("SERVIQ_TEST_API_BASE_URL", "http://127.0.0.1:18080/api/v1")
    monkeypatch.setenv("SERVIQ_VERIFICATION_HTTP_FIXTURE", json.dumps(fixture))
    for name in ("verify_frontend", "verify_incident_flow", "verify_settings_flow", "verify_jev_flow", "verify_capa_http"):
        monkeypatch.setitem(namespace, name, lambda *args, label=name: calls.append(label))
    monkeypatch.setitem(namespace, "verify_verification_http", lambda client, body: calls.append(("verification", body)))
    smoke_script["main"]()
    assert calls == ["verify_frontend", ("verification", fixture)]


def test_multi_http_mode_uses_real_worker_projection_boundary(smoke_script, monkeypatch):
    calls = []
    namespace = smoke_script["main"].__globals__
    fixture = {"incident_id": "fixture", "job_id": "job"}
    monkeypatch.setenv("SERVIQ_TEST_API_BASE_URL", "http://127.0.0.1:18080/api/v1")
    monkeypatch.setenv("SERVIQ_MULTI_AGENT_HTTP_FIXTURE", json.dumps(fixture))
    monkeypatch.setitem(namespace, "verify_frontend", lambda client: calls.append("frontend"))
    monkeypatch.setitem(namespace, "verify_multi_agent_http", lambda client, body: calls.append(("multi", body)))
    smoke_script["main"]()
    assert calls == ["frontend", ("multi", fixture)]


@pytest.mark.parametrize("capa", [False, True])
def test_http_smoke_modes_preserve_independent_validation(smoke_script, monkeypatch, capa):
    calls = []
    namespace = smoke_script["main"].__globals__
    monkeypatch.setenv("SERVIQ_TEST_API_BASE_URL", "http://127.0.0.1:18080/api/v1")
    fixture = {"incident_id": "fixture", "job_id": "job", "config_version": 1}
    if capa:
        monkeypatch.setenv("SERVIQ_CAPA_HTTP_FIXTURE", json.dumps(fixture))
    else:
        monkeypatch.delenv("SERVIQ_CAPA_HTTP_FIXTURE", raising=False)
    for name in ("verify_frontend", "verify_incident_flow", "verify_settings_flow", "verify_jev_flow", "verify_data_intake_http"):
        monkeypatch.setitem(namespace, name, lambda client, label=name: calls.append(label))
    monkeypatch.setitem(namespace, "verify_capa_http", lambda client, body: calls.append(("capa", body)))
    smoke_script["main"]()
    assert calls == (["verify_frontend", ("capa", fixture)] if capa else
                     ["verify_frontend", "verify_incident_flow", "verify_settings_flow", "verify_jev_flow", "verify_data_intake_http"])
