import ast
import json
from pathlib import Path

from src.agents.models import RCACandidate


def test_golden_three_cases_are_explicitly_simulated_and_match_smoke():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "data/golden/verification_closed_loop.json").read_text(encoding="utf-8"))
    script = ast.parse((root / "scripts/serviq_verification_smoke.py").read_text(encoding="utf-8"))
    cases = ast.literal_eval(next(node.value for node in script.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CASES" for t in node.targets)))
    assert data["execution_mode"] == "INTERNAL_RECORD_ONLY" and data["observation_mode"] == "SIMULATED"
    assert {(c["scenario_type"], c["expected_final_status"]) for c in data["cases"]} == {(r, s) for _, r, s in cases}
    assert all(c["approval_required"] and c["expected_required_evidence"] and c["acceptable_root_causes"] for c in data["cases"])
    assert all(c["acceptable_root_causes"] == [RCACandidate.model_fields["code"].default] for c in data["cases"])
