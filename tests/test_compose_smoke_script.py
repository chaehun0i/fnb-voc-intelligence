from pathlib import Path


def test_smoke_script_preserves_volumes_by_default() -> None:
    contents = Path("scripts/compose_smoke.ps1").read_text(encoding="utf-8")
    assert "docker compose up --build -d" in contents
    assert "pg_extension" in contents
    assert "docker compose stop" in contents
    assert "down -v" not in contents
