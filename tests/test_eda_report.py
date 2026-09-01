import subprocess
import sys
from pathlib import Path


def test_eda_report_cli_writes_json(tmp_path: Path) -> None:
    fixtures = Path(__file__).parent / "fixtures"
    output = tmp_path / "report.json"
    result = subprocess.run([sys.executable, "-m", "src.analysis.eda_report", "--products", str(fixtures / "sample_products.csv"), "--reviews", str(fixtures / "sample_reviews.csv"), "--output", str(output)], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert output.exists()
