"""ai/workflow/policy: 통합된 기능 책임, 기존 실행 계약 유지."""
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from src.ai.execution.models import CriterionResult, VerificationCandidate
from src.ai.workflow.models import (
    AgentContextPack,
    AgentDefinition,
    AgentSelection,
    CAPAProposal,
    EvidenceGap,
    SufficiencyPolicy,
    SufficiencyResult,
    WorkflowState,
)

RISK_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

AGENT_REGISTRY = tuple(AgentDefinition(agent_type=agent, business_label=label, purpose=purpose,
    required_capabilities=(capability,)) for agent, label, purpose, capability in (
    ("HISTORY", "과거 사례 조사", "RELATED_HISTORY", "HISTORY_DATA"),
    ("TRANSACTION", "거래 내역 조사", "TRANSACTION_SIGNALS", "TRANSACTION_DATA"),
    ("INVENTORY", "재고 조사", "INVENTORY_SIGNALS", "INVENTORY_DATA")))


def select_agents(candidates, capabilities, *, tenant_id, store, category,
                  allowed_agents, now, max_age=timedelta(minutes=5), registry=AGENT_REGISTRY):
    capabilities = tuple(sorted(capabilities, key=lambda c: c.capability))
    # Capability는 조직뿐 아니라 실제 조회 가능한 매장 범위에 묶습니다.
    if any(c.tenant_id != tenant_id or c.store != store for c in capabilities):
        raise ValueError("CAPABILITY_SCOPE_MISMATCH")
    if len({c.capability for c in capabilities}) != len(capabilities):
        raise ValueError("CAPABILITY_DUPLICATE")
    available = {c.capability for c in capabilities if c.available and c.health == "HEALTHY"
        and c.freshness == "FRESH" and timedelta(0) <= now-c.checked_at <= max_age}
    eligible = tuple(a for a in registry if a.agent_type in candidates)
    selected = tuple(a for a in eligible if a.enabled and a.parallel_safe
        and a.agent_type in allowed_agents and category in a.supported_categories
        and set(a.required_capabilities) <= available)
    return AgentSelection(selected=selected,
        excluded=tuple(a.agent_type for a in eligible if a not in selected), capabilities=tuple(capabilities))


def build_context(agent, *, tenant_id, incident_id, store, category, severity,
                  window_start, window_end, now, references=(), budget_bytes=4096,
                  freshness_hours=24):
    # 바이트 상한은 UTF-8 token 수의 보수적인 상한입니다. 원문 요약/지시를 입력받지 않습니다.
    grouped = {}
    for ref in sorted(references, key=lambda r: (r.source_ref,
            r.source_at.timestamp() if r.source_at else float("-inf"), r.provenance)):
        # 동일 참조의 새 시각이 오래된/미확인 시각을 덮어 freshness를 올리지 않습니다.
        grouped.setdefault(ref.source_ref, ref)
    refs = list(grouped.values())
    excluded = max(0, len(refs)-20)
    refs = refs[:20]
    while True:
        freshness = "UNKNOWN" if not refs or any(r.source_at is None for r in refs) else (
            "STALE" if any(r.source_at > now or now-r.source_at > timedelta(hours=freshness_hours)
                for r in refs) else "FRESH")
        document = {"agent_type": agent, "tenant_id": tenant_id, "incident_id": incident_id,
            "store": store, "category": category, "severity": severity, "objective": "READ_ONLY_INVESTIGATION",
            "data_policy": "REFERENCE_ONLY", "policy_version": "minimal-context-1",
            "window_start": window_start.isoformat().replace("+00:00", "Z"),
            "window_end": window_end.isoformat().replace("+00:00", "Z"),
            "fetched_at": now.isoformat().replace("+00:00", "Z"), "freshness": freshness,
            "references": [r.model_dump(mode="json") for r in refs], "excluded_count": excluded,
            "budget_bytes": budget_bytes}
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) <= budget_bytes:
            return AgentContextPack(**document, used_bytes=len(encoded), digest=hashlib.sha256(encoded).hexdigest())
        if not refs:
            raise ValueError("CONTEXT_BUDGET_EXHAUSTED")
        refs.pop()
        excluded += 1


def loop_policy(config):
    from src.ai.workflow.models import LoopPolicy
    from src.domain.config.resolution import ConfigResolver
    current = ConfigResolver().resolve(config).effective
    return LoopPolicy(max_iterations=min(3, current.max_agent_iterations),
        max_operations=current.max_tool_calls, token_budget=current.token_budget,
        cost_budget=current.cost_budget_usd, timeout_seconds=current.timeout_seconds)


def loop_termination(policy, state, *, now, started_at, before_refs=None):
    """Each operation is an actual read lookup; no synthetic MCP ToolCall is counted."""
    if (state.tool_call_count >= policy.max_operations or state.token_spent >= policy.token_budget
            or state.cost_spent >= policy.cost_budget
            or now-started_at >= timedelta(seconds=policy.timeout_seconds)):
        return "BUDGET_EXHAUSTED"
    if before_refs is not None and set(state.evidence_refs) <= set(before_refs):
        return "NO_NEW_EVIDENCE"
    if state.iteration >= policy.max_iterations:
        return "ITERATION_LIMIT"
    return None


def evidence_digest(refs):
    return hashlib.sha256(json.dumps(sorted(set(refs)), separators=(",", ":")).encode()).hexdigest()


def run_manifest(run):
    from pathlib import Path

    from src.ai.workflow.models import AgentRunManifest
    directory = Path(__file__).parent
    # An actual source bundle checksum, not an invented Git/AI Release version.
    sources = tuple(directory / name for name in ("models.py", "agents.py", "graph.py", "policy.py", "runtime.py"))
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in sources)).hexdigest()
    return AgentRunManifest(workflow_id=run.workflow_id, workflow_version=run.workflow_version,
        config_version=run.config_version, source_digest=digest,
        agent_versions=tuple((a.agent_type, a.agent_version)
            for a in (run.state.selection.selected if run.state.selection else ())))


def server_risk(*values):
    return max(("MEDIUM", *values), key=RISK_ORDER.index)


def approval_policy_digest(config):
    policy = {"risk": asdict(config.approval_policy_by_risk),
              "roles": sorted(config.required_roles), "separation": config.separation_of_duties,
              "critical_count": config.critical_approver_count, "auto_capa_draft": config.auto_capa_draft}
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evaluate_sufficiency(evidence, gaps=(), policy=None):
    policy = policy or SufficiencyPolicy()
    support = tuple(sorted({e.source_ref for e in evidence
        if e.stance == "SUPPORTING" and e.observation_code == "RELATED_HISTORY_MATCH"}))
    counter = tuple(sorted({e.source_ref for e in evidence if e.stance == "CONTRADICTING"}))
    dimensions = ("SOURCE_COVERAGE", "OBSERVATION_SUPPORT", "CONTRADICTION")
    if not evidence:
        status, reason = "INSUFFICIENT", "NO_EVIDENCE"
    elif counter:
        status, reason = "CONFLICTING", "CONFLICTING_EVIDENCE"
    elif len(support) < policy.minimum_sources or not set(policy.required_source_types).issubset(
            {e.source_type for e in evidence if e.source_ref in support}):
        status, reason = "INSUFFICIENT", "INSUFFICIENT_SOURCE_COVERAGE"
    else:
        status, reason = "SUFFICIENT", "SUFFICIENT_HISTORY_SUPPORT"
    generated = () if status == "SUFFICIENT" else (EvidenceGap(code=
        "CONFLICTING_EVIDENCE" if status == "CONFLICTING" else "INSUFFICIENT_SOURCE_COVERAGE"),)
    return SufficiencyResult(status=status, policy_version=policy.policy_version,
        evaluated_dimensions=dimensions, supporting_refs=support, contradicting_refs=counter,
        evidence_gaps=tuple(dict.fromkeys((*gaps, *generated))), reason_codes=(reason,))


def evaluate_verification(state: WorkflowState, now, *, window_hours=24):
    execution = state.execution
    if execution is None or len(state.capa_proposals) != 1:
        raise ValueError("VERIFICATION_EXECUTION_REQUIRED")
    action = state.capa_proposals[0]
    available = {e.source_ref for e in state.normalized_evidence}
    evidence = state.verification_evidence
    for e in evidence:
        if (e.tenant_id != state.tenant_id or e.agent_run_id != state.agent_run_id
                or e.execution_id != execution.execution_id or e.action_id != execution.action_id
                or e.store != action.store or not set(e.additional_evidence_refs) <= available):
            raise ValueError("VERIFICATION_EVIDENCE_LINEAGE_INVALID")
    reason = None
    if action.verification_criteria != CAPAProposal.model_fields["verification_criteria"].default:
        reason = "UNSUPPORTED_CRITERIA"
    elif not evidence:
        reason = "EVIDENCE_MISSING"
    elif any(e.observed_at < execution.completed_at or e.observed_at > now
             or now-e.observed_at > timedelta(hours=window_hours) for e in evidence):
        reason = "EVIDENCE_STALE"
    elif (len({e.review_record_present for e in evidence}) > 1
          or len({bool(e.additional_evidence_refs) for e in evidence}) > 1):
        reason = "EVIDENCE_CONFLICTING"
    if reason:
        results = ("INCONCLUSIVE", "INCONCLUSIVE")
    else:
        results = ("INCONCLUSIVE" if evidence[0].review_record_present is None else
                   "PASS" if evidence[0].review_record_present else "FAIL",
                   "PASS" if evidence[0].additional_evidence_refs else "FAIL")
    outcome = "INCONCLUSIVE" if "INCONCLUSIVE" in results else "FAIL" if "FAIL" in results else "PASS"
    summary = {"PASS": "내부 시뮬레이션 기록의 검증 기준을 충족했습니다.",
        "FAIL": "내부 시뮬레이션 기록의 검증 기준을 충족하지 못했습니다.",
        "INCONCLUSIVE": "조치 후 검증 근거가 부족하거나 상충합니다."}[outcome]
    candidate = VerificationCandidate(verification_id=str(uuid5(NAMESPACE_URL, "verification:"+execution.execution_id)),
        incident_id=state.incident_id, action_id=execution.action_id, execution_id=execution.execution_id,
        criteria=action.verification_criteria, evidence_ids=tuple(e.evidence_id for e in evidence),
        criterion_results=tuple(CriterionResult(code=code, result=value) for code, value in
            zip(("REVIEW_RECORD_PRESENT", "ADDITIONAL_EVIDENCE_LIST"), results, strict=True)),
        result=outcome, confidence=0 if outcome == "INCONCLUSIVE" else 1, summary=summary,
        reason_codes=(reason or ("CRITERIA_MET" if outcome == "PASS" else
            "CRITERIA_NOT_MET" if outcome == "FAIL" else "EVIDENCE_MISSING"),),
        verified_at=now, config_version=state.config_version)
    return WorkflowState.model_validate(state.model_copy(update={"verification": candidate}).model_dump(mode="json"))
