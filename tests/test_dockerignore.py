from pathlib import Path


def test_dockerignore_excludes_sensitive_and_local_artifacts() -> None:
    entries = set(Path(".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {".git", ".env", ".venv", "data/raw", "tests"} <= entries
    assert "src" not in entries and "pyproject.toml" not in entries
