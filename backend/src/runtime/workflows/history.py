"""검색 근거를 보존하며 선택적 정규화는 기존 Gateway만 사용합니다."""
import asyncio
import json
from datetime import timedelta

from src.domain.workflows.models import EvidenceCandidate, EvidenceGap, Finding
from src.llm.contracts import LLMIntent, LLMTaskType, ModelClass
from src.llm.errors import LLMError, LLMErrorCode


class HistoryInvestigation:
    def __init__(self, search, *, store, query, resolved, requires_llm, clock, executor=None):
        self.search, self.store, self.query = search, store, query
        self.resolved, self.requires_llm, self.clock, self.executor = resolved, requires_llm, clock, executor

    def __call__(self, state):
        config = self.resolved.effective
        if (config.max_tool_calls < 1 or state.tool_call_count >= config.max_tool_calls
                or state.iteration >= config.max_agent_iterations):
            raise ValueError("검색 호출 예산을 초과했습니다.")
        if callable(getattr(type(self.search), "search_evidence", None)):
            candidates = tuple(self.search.search_evidence(state.tenant_id, self.store, self.query))
        else:
            # 기존 참조 전용 adapter는 사실/관련성을 새로 꾸미지 않습니다.
            candidates = tuple(EvidenceCandidate(source_ref=ref, rank=rank, retrieved_at=self.clock(),
                tenant_id=state.tenant_id, store=self.store)
                for ref, rank in self.search.search(state.tenant_id, self.store, self.query))
        refs = tuple(c.source_ref for c in candidates)
        gaps = () if refs else (EvidenceGap(code="NO_AUTHORIZED_HISTORY"),)
        tokens, cost = 0, 0.0
        if refs and self.requires_llm and self.executor is None:
            gaps += (EvidenceGap(code="LLM_UNAVAILABLE"),)
        # 검색만으로 충분하거나 Jev가 LLM을 요구하지 않으면 외부 호출하지 않습니다.
        if refs and self.requires_llm and self.executor is not None:
            schema = {"type": "object", "properties": {"needs_more_history": {"type": "boolean"}},
                      "required": ["needs_more_history"], "additionalProperties": False}
            intent = LLMIntent(request_id=state.agent_run_id, correlation_id=state.workflow_id,
                tenant_id=state.tenant_id, incident_id=state.incident_id, task_type=LLMTaskType.SUMMARY,
                model_class=ModelClass.FAST, input_references=refs,
                payload_json=json.dumps({"evidence_count": len(refs), "evidence_refs": refs}),
                output_schema_json=json.dumps(schema), schema_version="history-1",
                prompt_template="history-evidence-sufficiency", prompt_version="1",
                config_version=state.config_version, deadline=self.clock()+timedelta(seconds=config.timeout_seconds),
                token_budget=config.token_budget, cost_budget_usd=config.cost_budget_usd,
                max_output_tokens=min(256, config.token_budget), fallback_allowed=config.llm_fallback_allowed,
                free_text_reviewed=True)
            try:
                result = asyncio.run(self.executor.execute(intent, self.resolved))
                tokens, cost = result.usage.total_tokens, result.estimated_cost_usd
                # 생성 문장은 증거가 아닙니다. 구조화된 보조 판정만 남깁니다.
                if json.loads(result.structured_json)["needs_more_history"]:
                    gaps += (EvidenceGap(code="NO_AUTHORIZED_HISTORY"),)
            except LLMError as error:
                if error.code == LLMErrorCode.TRACE_UNAVAILABLE:
                    raise
                gaps += (EvidenceGap(code="LLM_POLICY_DENIED" if error.code == LLMErrorCode.POLICY_DENIED else "LLM_UNAVAILABLE"),)
        return state.model_copy(update={"findings": (Finding(evidence_refs=refs),) if refs else (),
            "evidence_refs": refs, "evidence_candidates": candidates, "evidence_gaps": gaps,
            "iteration": state.iteration+1, "tool_call_count": state.tool_call_count+1,
            "token_spent": tokens, "cost_spent": cost})
