import os
import subprocess
import sys

import pytest
from psycopg import OperationalError

from src import config, health


def test_health_returns_failure_without_database_url(monkeypatch: object) -> None:
    monkeypatch.setattr(config.settings, "postgresql_url", None)
    monkeypatch.setattr(health, "connect", lambda _url: None)
    assert health.main() == 1


@pytest.mark.parametrize("ready", [True, False])
def test_health_checks_database_and_closes_connection(monkeypatch, ready) -> None:
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(config.settings, "postgresql_url", "postgresql://health/test")
    monkeypatch.setattr(health, "connect", lambda _url: connection)
    monkeypatch.setattr(
        health, "check_health", lambda actual: ready if actual is connection else False
    )
    assert health.main() == (0 if ready else 1)
    assert connection.closed


def test_health_connection_failure_has_no_traceback(monkeypatch) -> None:
    def unavailable(_url):
        raise OperationalError("테스트용 연결 실패")

    monkeypatch.setattr(config.settings, "postgresql_url", "postgresql://health/test")
    monkeypatch.setattr(health, "connect", unavailable)
    assert health.main() == 1


@pytest.mark.parametrize("failure_stage", ["query", "close"])
def test_health_query_and_close_failures_are_safe(monkeypatch, capsys, failure_stage):
    class Connection:
        closed = False

        def close(self):
            self.closed = True
            if failure_stage == "close":
                raise OperationalError("테스트용 민감한 연결 정보")

    def check(_connection):
        if failure_stage == "query":
            raise OperationalError("테스트용 민감한 연결 정보")
        return True

    connection = Connection()
    monkeypatch.setattr(config.settings, "postgresql_url", "postgresql://health/test")
    monkeypatch.setattr(health, "connect", lambda _url: connection)
    monkeypatch.setattr(health, "check_health", check)
    assert health.main() == 1
    assert connection.closed
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


def test_health_module_reports_missing_configuration(tmp_path) -> None:
    environment = os.environ.copy()
    environment.pop("POSTGRESQL_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "src.health"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    environment["POSTGRESQL_URL"] = "invalid-test-connection-string"
    invalid = subprocess.run(
        [sys.executable, "-m", "src.health"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid.returncode == 1
    assert "invalid-test-connection-string" not in invalid.stderr
    assert "Traceback" not in invalid.stderr
