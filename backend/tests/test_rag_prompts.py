import pytest

from src.rag.context import RagContext, RagContextItem
from src.rag.prompts import (
    INSUFFICIENT_EVIDENCE_TEXT,
    PROMPT_VERSION,
    build_voc_prompt,
)


def test_grounded_prompt_is_versioned_and_deterministic() -> None:
    context = RagContext(
        items=[
            RagContextItem(
                review_id="R1",
                text="가격이 비싸요",
                product_id="P1",
                category="beverage",
                pain_points=["price"],
                rank=1,
            )
        ]
    )
    first = build_voc_prompt("가격 불만은?", context)
    assert first == build_voc_prompt("가격 불만은?", context)
    assert f"prompt_version={PROMPT_VERSION}" in first
    assert "review_id=R1" in first and "text=가격이 비싸요" in first
    assert "리뷰 근거만 사용" in first
    assert INSUFFICIENT_EVIDENCE_TEXT in first


def test_prompt_explicitly_represents_missing_evidence() -> None:
    prompt = build_voc_prompt("질문", RagContext())
    assert "(근거 없음)" in prompt


def test_prompt_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="query"):
        build_voc_prompt(" ", RagContext())
