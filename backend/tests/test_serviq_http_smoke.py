"""HTTP smoke의 명시적 로컬 실행 조건을 외부 요청 없이 검증합니다."""

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
