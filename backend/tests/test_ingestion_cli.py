import json
from pathlib import Path

from src.ingestion.cli import main


def test_cli_prints_concise_dry_run_summary(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "source.json"
    path.write_text('[{"id":"1"},{"id":"2"}]', encoding="utf-8")
    assert main(["--source-type", "json", "--path", str(path), "--mapping", '{"id":"id"}', "--dry-run", "--limit", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["input_count"] == 1
