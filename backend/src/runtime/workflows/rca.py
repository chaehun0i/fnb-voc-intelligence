"""제한된 History 가설만 생성하며 Domain 상태를 변경하지 않습니다."""
import asyncio
import json
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from src.domain.workflows.models import EvidenceGap, RCACandidate
from src.llm.contracts import LLMIntent, LLMTaskType, ModelClass
from src.llm.errors import LLMError, LLMErrorCode
from src.llm.structured import schema_validator, validate_output


def validate_candidate(candidate, evidence):
    available = {e.source_ref: e for e in evidence}
    if (not set(candidate.supporting_refs+candidate.contradicting_refs).issubset(available)
            or any(available[r].stance != "SUPPORTING" for r in candidate.supporting_refs)
            or any(available[r].stance != "CONTRADICTING" for r in candidate.contradicting_refs)):
        raise ValueError("RCA는 검증된 지지·반대 근거만 참조해야 합니다.")
    return candidate


class RCAInvestigation:
    def __init__(self, resolved, decision_id, *, requires_llm, clock, executor=None, deadline=None):
        self.resolved, self.decision_id = resolved, decision_id
        self.requires_llm, self.clock, self.executor = requires_llm, clock, executor
        self.deadline = deadline

    def __call__(self, state):
        if state.sufficiency is None or not state.sufficiency.allows_rca:
            return state
        config = self.resolved.effective
        if not config.auto_rca_draft:
            return self.gap(state, "RCA_DISABLED")
        if state.iteration >= config.max_agent_iterations or (self.deadline and self.clock() >= self.deadline):
            return self.gap(state, "RCA_BUDGET_EXHAUSTED")
        refs = state.sufficiency.supporting_refs
        confidence, tokens, cost = .5, 0, 0.0
        request_id = str(uuid5(NAMESPACE_URL, "rca:"+state.agent_run_id))
        if self.requires_llm:
            if any(g.code in {"LLM_POLICY_DENIED", "LLM_UNAVAILABLE"} for g in state.evidence_gaps):
                return state
            if self.executor is None:
                return self.gap(state, "LLM_UNAVAILABLE")
            if config.token_budget <= state.token_spent or config.cost_budget_usd <= state.cost_spent:
                return self.gap(state, "RCA_BUDGET_EXHAUSTED")
            schema = {"type": "object", "properties": {
                "code": {"type": "string", "enum": ["REPEATED_HISTORY_SIGNAL"]},
                "supporting_refs": {"type": "array", "items": {"type": "string", "enum": list(refs)}, "minItems": 1},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
                "required": ["code", "supporting_refs", "confidence"], "additionalProperties": False}
            intent = LLMIntent(request_id=request_id, correlation_id=state.workflow_id, tenant_id=state.tenant_id,
                incident_id=state.incident_id, task_type=LLMTaskType.RCA, model_class=ModelClass.STANDARD,
                input_references=refs, payload_json=json.dumps({"evidence_refs": refs,
                    "observations": [{"ref": e.source_ref, "code": e.observation_code} for e in state.normalized_evidence]}),
                output_schema_json=json.dumps(schema), schema_version="rca-history-1",
                prompt_template="history-grounded-rca", prompt_version="1", config_version=state.config_version,
                deadline=self.deadline or self.clock()+timedelta(seconds=config.timeout_seconds),
                token_budget=config.token_budget-state.token_spent, cost_budget_usd=config.cost_budget_usd-state.cost_spent,
                max_output_tokens=min(256, config.token_budget-state.token_spent),
                fallback_allowed=config.llm_fallback_allowed, free_text_reviewed=True)
            def domain_validate(value):
                if not value["supporting_refs"] or not set(value["supporting_refs"]).issubset(refs):
                    raise ValueError("근거 참조를 확인해 주세요.")
            try:
                result = asyncio.run(self.executor.execute(intent, self.resolved, domain_validator=domain_validate))
                value = json.loads(validate_output(result.structured_json,
                    schema_validator(intent.output_schema_json), domain_validate))
                refs, confidence = tuple(value["supporting_refs"]), value["confidence"]
                tokens, cost = result.usage.total_tokens, result.estimated_cost_usd
            except LLMError as error:
                if error.code == LLMErrorCode.TRACE_UNAVAILABLE:
                    raise
                return self.gap(state, "LLM_POLICY_DENIED" if error.code == LLMErrorCode.POLICY_DENIED else "LLM_UNAVAILABLE")
        candidate = validate_candidate(RCACandidate(candidate_id=request_id, supporting_refs=refs,
            confidence=confidence, unresolved_gaps=state.evidence_gaps,
            generated_by="LLM_GATEWAY" if self.requires_llm else "DETERMINISTIC",
            config_version=state.config_version, jev_decision_id=self.decision_id,
            llm_request_id=request_id if self.requires_llm else None), state.normalized_evidence)
        return state.model_copy(update={"rca_candidates": (candidate,),
            "token_spent": state.token_spent+tokens, "cost_spent": state.cost_spent+cost,
            "iteration": state.iteration+1})

    @staticmethod
    def gap(state, code):
        return state.model_copy(update={"evidence_gaps": (*state.evidence_gaps, EvidenceGap(code=code))})
