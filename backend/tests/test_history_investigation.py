"""원본 참조·근거 부족·LLM 불필요 경로를 검증합니다."""
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from src.agents.history_node import HistoryInvestigation
from src.agents.models import WorkflowState
from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver


def state():
    return WorkflowState(tenant_id="a", incident_id="i", workflow_id=str(uuid4()),
        agent_run_id=str(uuid4()), risk_level="LOW", route="GENERAL_INVESTIGATION", config_version=1)


def test_refs_not_generated_answer_and_no_unneeded_llm():
    search, executor = Mock(), Mock()
    search.search.return_value = [("review:r1", 1)]
    investigate = HistoryInvestigation(search, store="매장", query="quality",
        resolved=ConfigResolver().resolve(RuntimeConfig()), requires_llm=False,
        clock=lambda: datetime(2026, 10, 5, tzinfo=UTC), executor=executor)
    result = investigate(state())
    assert result.evidence_refs == ("review:r1",)
    assert result.findings[0].evidence_refs == result.evidence_refs
    assert result.token_spent == 0 and result.tool_call_count == 1
    executor.execute.assert_not_called()
    search.search.assert_called_once_with("a", "매장", "quality")


def test_no_history_is_gap_not_invented_evidence():
    search = Mock()
    search.search.return_value = []
    result = HistoryInvestigation(search, store="매장", query="quality",
        resolved=ConfigResolver().resolve(RuntimeConfig()), requires_llm=True,
        clock=lambda: datetime(2026, 10, 5, tzinfo=UTC))(state())
    assert result.findings == () and result.evidence_candidates == ()
    assert result.evidence_gaps[0].code == "NO_AUTHORIZED_HISTORY"
