from pathlib import Path


def test_compose_defines_pgvector_with_persistent_volume() -> None:
    contents = Path("compose.yaml").read_text(encoding="utf-8")
    assert "pgvector/pgvector" in contents
    assert "postgres_data" in contents and "pg_isready" in contents


def test_app_service_uses_database_network_configuration() -> None:
    contents = Path("compose.yaml").read_text(encoding="utf-8")
    assert "app:" in contents and "condition: service_healthy" in contents


def test_compose_wires_idempotent_database_initializer() -> None:
    assert "init-db:" in Path("compose.yaml").read_text(encoding="utf-8")


def test_compose_offers_reusable_cli_service() -> None:
    contents = Path("compose.yaml").read_text(encoding="utf-8")
    assert "cli:" in contents and 'profiles: ["cli"]' in contents
