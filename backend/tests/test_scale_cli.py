import json

from src.rag.scale_cli import main
from src.rag.scale_metrics import ScaleProgress
from src.rag.scale_models import ScaleJobConfig


def test_scale_cli_passes_all_options_and_prints_progress(capsys: object) -> None:
    captured: dict[str, ScaleJobConfig] = {}

    def runner(config: ScaleJobConfig, callback: object) -> ScaleProgress:
        captured["config"] = config
        event = ScaleProgress(2, 1, 1, 0, 1.0, 2.0)
        callback(event)
        return event

    assert main(
        ["--batch-size", "20", "--workers", "2", "--retries", "4", "--resume", "--limit", "30"],
        runner=runner,
    ) == 0
    assert captured["config"] == ScaleJobConfig(20, 2, 4, True, 30)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and json.loads(lines[-1])["throughput_per_second"] == 2.0


def test_scale_cli_returns_failure_status() -> None:
    assert main(
        [],
        runner=lambda _config, _callback: ScaleProgress(1, 0, 0, 1, 1.0, 1.0),
    ) == 1
