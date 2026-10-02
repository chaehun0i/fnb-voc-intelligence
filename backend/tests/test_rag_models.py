import pytest
from pydantic import ValidationError

from src.rag.rag_models import RagAnswer, RagRetrievalMetadata, RagSource


def test_answer_keeps_generated_text_separate_from_sources() -> None:
    source = RagSource(
        review_id="R1",
        rank=1,
        lexical_rank=2,
        vector_rank=1,
        match_source="both",
        metadata={"category": "beverage"},
    )
    answer = RagAnswer(
        answer="가격 불만이 있습니다. [R1]",
        status="success",
        sources=[source],
        retrieval=RagRetrievalMetadata(
            mode="hybrid", top_k=5, retrieved_count=3, context_count=1
        ),
        generator_model="fake-v1",
        prompt_version="fnb-voc-rag-v1",
    )
    assert answer.sources[0].review_id == "R1"
    assert answer.sources[0].metadata["category"] == "beverage"
    assert answer.retrieval.retrieved_count == 3


def test_success_requires_traceable_source() -> None:
    with pytest.raises(ValidationError, match="requires sources"):
        RagAnswer(
            answer="unsupported",
            status="success",
            retrieval=RagRetrievalMetadata(
                mode="hybrid", top_k=5, retrieved_count=0, context_count=0
            ),
            prompt_version="v1",
        )


def test_source_and_retrieval_counts_are_validated() -> None:
    with pytest.raises(ValidationError):
        RagSource(review_id="", rank=0)
    with pytest.raises(ValidationError):
        RagRetrievalMetadata(
            mode="hybrid", top_k=0, retrieved_count=-1, context_count=0
        )
