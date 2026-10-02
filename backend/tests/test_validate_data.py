import subprocess
import sys
from pathlib import Path


def test_validation_cli_passes_for_fixtures() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    result = subprocess.run([sys.executable, "-m", "src.data.validate_data", "--products", str(fixtures / "sample_products.csv"), "--reviews", str(fixtures / "sample_reviews.csv")], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "Validation passed" in result.stdout
