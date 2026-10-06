"""검색 관련성은 원인 확정이 아니라 제한된 History 가설의 근거입니다."""
from src.agents.models import (
    EvidenceGap,
    SufficiencyPolicy,
    SufficiencyResult,
)


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
