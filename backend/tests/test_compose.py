from pathlib import Path

COMPOSE = Path(__file__).parents[2] / "compose.yaml"


def test_compose_defines_pgvector_with_persistent_volume() -> None:
    contents = COMPOSE.read_text(encoding="utf-8")
    assert "pgvector/pgvector" in contents
    assert "postgres_data" in contents and "pg_isready" in contents


def test_app_service_uses_database_network_configuration() -> None:
    contents = COMPOSE.read_text(encoding="utf-8")
    assert "app:" in contents and "condition: service_healthy" in contents


def test_compose_wires_idempotent_database_initializer() -> None:
    assert "init-db:" in COMPOSE.read_text(encoding="utf-8")


def test_compose_offers_reusable_cli_service() -> None:
    contents = COMPOSE.read_text(encoding="utf-8")
    assert "cli:" in contents and 'profiles: ["cli"]' in contents


def test_compose_exposes_dashboard_after_database_readiness() -> None:
    contents = COMPOSE.read_text(encoding="utf-8")
    assert "dashboard:" in contents and "DASHBOARD_PORT" in contents
