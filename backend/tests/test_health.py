from src import health


def test_health_returns_failure_without_database_url(monkeypatch: object) -> None:
    monkeypatch.setattr(health, "connect", lambda _url: None)
