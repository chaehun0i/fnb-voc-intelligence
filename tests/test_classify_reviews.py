import subprocess
import sys
from pathlib import Path


def test_classification_cli_writes_output(tmp_path: Path) -> None:
    fixtures = Path(__file__).parent / "fixtures"
    output = tmp_path / "classification.json"
    result = subprocess.run([sys.executable, "-m", "src.analysis.classify_reviews", "--products", str(fixtures / "sample_products.csv"), "--reviews", str(fixtures / "sample_reviews.csv"), "--output", str(output)], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert output.exists()
