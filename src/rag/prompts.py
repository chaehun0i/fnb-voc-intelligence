"""Versioned grounded prompt for F&B voice-of-customer analysis."""

from .context import RagContext

PROMPT_VERSION = "fnb-voc-rag-v1"
INSUFFICIENT_EVIDENCE_TEXT = "근거가 충분하지 않습니다."


def build_voc_prompt(query: str, context: RagContext) -> str:
    if not query.strip():
        raise ValueError("query must not be empty")
    evidence = []
    for item in context.items:
        evidence.append(
            " | ".join(
                (
                    f"review_id={item.review_id}",
                    f"product_id={item.product_id or '-'}",
                    f"category={item.category or '-'}",
                    f"pain_points={','.join(item.pain_points) or '-'}",
                    f"text={item.text}",
                )
            )
        )
    evidence_block = "\n".join(evidence) if evidence else "(근거 없음)"
    return f"""[prompt_version={PROMPT_VERSION}]
당신은 식음료 VOC 분석가입니다.
아래 제공된 리뷰 근거만 사용해 한국어로 답하세요.
근거에 없는 사실을 추측하거나 일반 지식으로 보완하지 마세요.
주요 주장에는 반드시 [review_id]를 붙이세요.
근거가 없거나 질문을 뒷받침하기 부족하면 정확히 다음 문장만 답하세요:
{INSUFFICIENT_EVIDENCE_TEXT}

[질문]
{query.strip()}

[리뷰 근거]
{evidence_block}
"""
