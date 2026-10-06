"""ai/workflow/policy: 통합된 기능 책임, 기존 실행 계약 유지."""
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from src.ai.execution.models import CriterionResult, VerificationCandidate
from src.ai.workflow.models import (
    CAPAProposal,
    EvidenceGap,
    SufficiencyPolicy,
    SufficiencyResult,
    WorkflowState,
)

RISK_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


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
