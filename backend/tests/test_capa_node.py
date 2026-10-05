from dataclasses import replace

from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver
from src.runtime.workflows.capa import CAPAInvestigation
from tests.test_rca_investigation import node, ready


def test_deterministic_grounded_capa_and_server_risk():
    state = node()(ready())
    capa = CAPAInvestigation(ConfigResolver().resolve(replace(RuntimeConfig(), auto_capa_draft=True)),
        "decision", store="s", incident_severity="HIGH")
    result = capa(state)
    assert result == capa(state) and len(result.capa_proposals) == 1
    proposal = result.capa_proposals[0]
    assert proposal.risk_level == "HIGH" and proposal.supporting_evidence_ids == state.rca_candidates[0].supporting_refs
    assert proposal.verification_criteria and result.token_spent == state.token_spent
    assert not capa(ready()).capa_proposals


def test_disabled_capa_never_generates():
    capa = CAPAInvestigation(ConfigResolver().resolve(RuntimeConfig()), "decision", store="s", incident_severity="LOW")
    assert not capa(node()(ready())).capa_proposals
