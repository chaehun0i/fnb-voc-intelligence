"""기존 Graph를 확장하며 불충분 경로는 RCA를 건너뜁니다."""
from unittest.mock import Mock

from src.domain.workflows.sufficiency import evaluate_sufficiency
from src.runtime.workflows.checkpoint import memory_checkpoint
from src.runtime.workflows.graph import history_graph, invoke_or_resume
from tests.test_rca_investigation import node, ready


def test_sufficient_path_and_checkpoint_restore():
    initial = ready()
    rca = Mock(side_effect=node())
    saver = memory_checkpoint()
    graph = history_graph(saver, lambda s: s, lambda s: None, normalize=lambda s: s,
        evaluate=lambda s: s, rca=rca)
    result = invoke_or_resume(graph, initial)
    assert result.rca_candidates and result.status == "COMPLETED"
    assert invoke_or_resume(graph, initial) == result
    assert rca.call_count == 1


def test_insufficient_path_never_calls_rca():
    initial = ready().model_copy(update={"normalized_evidence": (), "sufficiency": evaluate_sufficiency(())})
    rca = Mock()
    result = invoke_or_resume(history_graph(memory_checkpoint(), lambda s: s, lambda s: None,
        normalize=lambda s: s, evaluate=lambda s: s, rca=rca), initial)
    assert not result.rca_candidates and result.sufficiency.status == "INSUFFICIENT"
    rca.assert_not_called()
