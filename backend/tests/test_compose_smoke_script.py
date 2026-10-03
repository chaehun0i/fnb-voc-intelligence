from pathlib import Path


def test_smoke_script_preserves_volumes_by_default() -> None:
    script = Path(__file__).parents[2] / "scripts" / "compose_smoke.ps1"
    contents = script.read_text(encoding="utf-8")
    assert "docker compose up --build -d" in contents
    assert "pg_extension" in contents
    assert "docker compose stop" in contents
    assert "down -v" not in contents


def test_smoke_checks_native_exit_codes_and_real_extension() -> None:
    script = Path(__file__).parents[2] / "scripts" / "compose_smoke.ps1"
    contents = script.read_text(encoding="utf-8")
    assert "from src.init_db import main" in contents
    assert "python -m src.health" in contents
    assert "$LASTEXITCODE -ne 0" in contents
    assert "$extension.Trim() -ne '1'" in contents
