from pathlib import Path


def test_compose_defines_pgvector_with_persistent_volume() -> None:
    contents = Path("compose.yaml").read_text(encoding="utf-8")
    assert "pgvector/pgvector" in contents
    assert "postgres_data" in contents and "pg_isready" in contents
