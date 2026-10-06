"""ai/workflow/agents: 통합된 기능 책임, 기존 실행 계약 유지."""
import asyncio
import json
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from src.ai.intelligence.models import (
    LLMError,
    LLMErrorCode,
    LLMIntent,
    LLMTaskType,
    ModelClass,
)
from src.ai.intelligence.service import schema_validator, validate_output
from src.ai.workflow.models import (
    CAPAProposal,
    EvidenceCandidate,
    EvidenceGap,
    Finding,
    InvestigationResult,
    NormalizedEvidence,
    RCACandidate,
    WorkflowState,
)
from src.ai.workflow.policy import server_risk
from src.application.security.principal import AccessError


class SourceUnavailable(OSError):
    """Adapter 원문 오류를 노출하지 않는 read source 장애입니다."""


def branch_gap(context, branch_id, clock, *, code, status="FAILED", retryable=False, started=None):
    return InvestigationResult(agent_type=context.agent_type, branch_id=branch_id,
        tenant_id=context.tenant_id, incident_id=context.incident_id, store=context.store,
        status=status, evidence_gaps=(EvidenceGap(code=code, agent_type=context.agent_type),),
        retryable=retryable, uncertainty="MISSING_EVIDENCE", started_at=started or clock(),
        completed_at=clock(), context_digest=context.digest)


def isolated_branch(action, context, branch_id, *, clock, deadline):
    started = clock()
    if started >= deadline:
        return branch_gap(context, branch_id, clock, code="BRANCH_BUDGET_EXHAUSTED", started=started)
    try:
        result = InvestigationResult.model_validate(action(context, branch_id).model_dump(mode="json"))
    except TimeoutError:
        return branch_gap(context, branch_id, clock, code="BRANCH_FAILED", retryable=True, started=started)
    except SourceUnavailable:
        return branch_gap(context, branch_id, clock, code="SOURCE_UNAVAILABLE", retryable=True, started=started)
    except RuntimeError:
        return branch_gap(context, branch_id, clock, code="BRANCH_FAILED", started=started)
    # Authorization/validation/checkpoint 오류는 branch partial success로 바꾸지 않습니다.
    if (result.tenant_id != context.tenant_id or result.store != context.store
            or result.incident_id != context.incident_id or result.context_digest != context.digest
            or result.agent_type != context.agent_type or result.branch_id != branch_id):
        raise AccessError()
    if clock() >= deadline:
        return branch_gap(context, branch_id, clock, code="BRANCH_BUDGET_EXHAUSTED", started=started)
    if any(e.source_at is None or e.source_at > context.window_end
            or (context.agent_type != "HISTORY" and e.source_at < context.window_start)
            for e in result.evidence_candidates):
        return branch_gap(context, branch_id, clock, code="SOURCE_STALE", status="STALE", started=started)
    return result


class OperationalInvestigation:
    def __init__(self, source, clock):
        self.source, self.clock = source, clock

    def __call__(self, context, branch_id):
        started = self.clock()
        observations = self.source.observations(context)
        if any(o.tenant_id != context.tenant_id or o.store != context.store
                or o.agent_type != context.agent_type for o in observations):
            raise AccessError()
        candidates = tuple(EvidenceCandidate(source_ref=o.source_ref, source_type=context.agent_type,
            tenant_id=o.tenant_id, store=o.store, rank=rank, source_at=o.observed_at,
            retrieved_at=self.clock(), provenance=("synthetic_operational",),
            observation_code=o.signal, stance=o.stance) for rank, o in enumerate(observations, 1))
        return InvestigationResult(agent_type=context.agent_type, branch_id=branch_id,
            tenant_id=context.tenant_id, incident_id=context.incident_id, store=context.store,
            status="SUCCESS" if candidates else "NO_EVIDENCE", evidence_candidates=candidates,
            findings=(Finding(code=context.agent_type+"_SIGNAL_FOUND", evidence_refs=tuple(e.source_ref for e in candidates)),)
                if candidates else (),
            evidence_gaps=() if candidates else (EvidenceGap(code="NO_EVIDENCE_FOUND", agent_type=context.agent_type),),
            uncertainty="OBSERVATIONS_NOT_CAUSE" if candidates else "MISSING_EVIDENCE",
            started_at=started, completed_at=self.clock(), context_digest=context.digest)


def normalize_evidence(candidates, *, tenant_id, store, agent_run_id, preserve_conflicts=False):
    grouped = {}
    for value in candidates:
        item = EvidenceCandidate.model_validate(value.model_dump(mode="json"))
        if item.tenant_id != tenant_id or item.store != store:
            raise AccessError()
        previous = grouped.get(item.source_ref)
        if previous:
            if previous.stance != item.stance or previous.observation_code != item.observation_code:
                if not preserve_conflicts:
                    raise ValueError("같은 출처의 상충 관측은 정규화 전에 해결해야 합니다.")
                item = item.model_copy(update={"stance": "CONTRADICTING", "observation_code": "REFERENCE_ONLY"})
            item = item.model_copy(update={"rank": min(item.rank, previous.rank),
                "provenance": tuple(sorted(set(item.provenance+previous.provenance))),
                "observed_stances": tuple(sorted(set(item.observed_stances+previous.observed_stances))),
                "contributing_agents": tuple(sorted(set(item.contributing_agents+previous.contributing_agents))),
                "retrieved_at": min(item.retrieved_at, previous.retrieved_at),
                "source_at": min(item.source_at, previous.source_at) if item.source_at and previous.source_at else None})
        grouped[item.source_ref] = item
    return tuple(NormalizedEvidence(**item.model_dump(), source_id=item.source_ref.split(":", 1)[1],
        step_name="investigation_fan_in" if preserve_conflicts else "history_investigation",
        agent_run_id=agent_run_id) for item in sorted(grouped.values(), key=lambda e: (e.rank, e.source_ref)))


def investigation_fan_in(state):
    state = WorkflowState.model_validate(state.model_dump(mode="json"))
    if state.selection is None or {b.agent_type for b in state.branches} != {a.agent_type for a in state.selection.selected}:
        raise ValueError("BRANCH_RESULTS_INCOMPLETE")
    candidates, findings, gaps = [], [], list(state.evidence_gaps)
    for branch in sorted(state.branches, key=lambda b: b.agent_type):
        findings.extend(branch.findings)
        gaps.extend(branch.evidence_gaps)
        for e in branch.evidence_candidates:
            candidates.append(e.model_copy(update={"observed_stances": (e.stance,),
                "contributing_agents": (branch.agent_type,)}))
    gaps.extend(EvidenceGap(code="CAPABILITY_UNAVAILABLE", agent_type=a) for a in state.selection.excluded)
    store = state.contexts[0].store if state.contexts else state.selection.capabilities[0].store
    evidence = normalize_evidence(candidates, tenant_id=state.tenant_id, store=store,
        agent_run_id=state.agent_run_id, preserve_conflicts=True)
    # 전체 Evidence/Checkpoint 상한은 기존 20건 계약을 유지합니다.
    evidence = evidence[:20]
    refs = tuple(e.source_ref for e in evidence)
    findings = tuple(f.model_copy(update={"evidence_refs": tuple(r for r in f.evidence_refs if r in refs)})
        for f in findings if set(f.evidence_refs) & set(refs))
    candidates = tuple(EvidenceCandidate.model_validate(e.model_dump(exclude={"source_id", "agent_run_id", "step_name"})) for e in evidence)
    result = state.model_copy(update={"normalized_evidence": evidence, "evidence_candidates": candidates,
        "branches": tuple(sorted(state.branches, key=lambda b: b.agent_type)),
        "evidence_refs": refs, "findings": findings, "evidence_gaps": tuple(dict.fromkeys(gaps)),
        "tool_call_count": state.tool_call_count+len(state.branches), "iteration": state.iteration+1})
    return WorkflowState.model_validate(result.model_dump(mode="json"))


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
        if (state.loop is None and state.iteration >= config.max_agent_iterations) or (self.deadline and self.clock() >= self.deadline):
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
            "iteration": state.iteration if state.loop else state.iteration+1})

    @staticmethod
    def gap(state, code):
        return state.model_copy(update={"evidence_gaps": (*state.evidence_gaps, EvidenceGap(code=code))})


class CAPAInvestigation:
    def __init__(self, resolved, decision_id, *, store, incident_severity):
        self.resolved, self.decision_id = resolved, decision_id
        self.store, self.incident_severity = store, incident_severity

    def __call__(self, state):
        state = WorkflowState.model_validate(state.model_dump(mode="json"))
        if state.capa_proposals and all(p.status == "APPLIED" for p in state.capa_proposals):
            # checkpoint 재시도는 Application에 반영된 조치와 Approval lineage를 보존합니다.
            return state
        if (not self.resolved.effective.auto_capa_draft or state.sufficiency is None
                or not state.sufficiency.allows_rca or not state.rca_candidates):
            return state
        risk = server_risk(state.risk_level, self.incident_severity)
        proposals = tuple(CAPAProposal(
            capa_proposal_id=str(uuid5(NAMESPACE_URL, "capa:"+state.agent_run_id+":"+c.candidate_id)),
            tenant_id=state.tenant_id, store=self.store, incident_id=state.incident_id,
            agent_run_id=state.agent_run_id, rca_candidate_id=c.candidate_id,
            risk_level=risk, supporting_evidence_ids=c.supporting_refs,
            target_reference=state.incident_id, config_version=state.config_version,
            decision_reference=self.decision_id) for c in sorted(state.rca_candidates, key=lambda c: c.candidate_id)[:3])
        return WorkflowState.model_validate(state.model_copy(update={"capa_proposals": proposals}).model_dump(mode="json"))
