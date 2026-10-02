from pathlib import Path


def test_dockerfile_uses_non_root_python_runtime() -> None:
    contents = (Path(__file__).parents[2] / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.12-slim" in contents
    assert "USER app" in contents
