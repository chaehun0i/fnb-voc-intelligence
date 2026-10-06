export const gapCodes = ["NO_AUTHORIZED_HISTORY", "LLM_POLICY_DENIED", "LLM_UNAVAILABLE", "INSUFFICIENT_SOURCE_COVERAGE", "CONFLICTING_EVIDENCE", "RCA_DISABLED", "RCA_BUDGET_EXHAUSTED", "CAPABILITY_UNAVAILABLE", "SOURCE_UNAVAILABLE", "SOURCE_STALE", "BRANCH_FAILED", "NO_EVIDENCE_FOUND", "BRANCH_BUDGET_EXHAUSTED"] as const;
export type EvidenceGap = { code: typeof gapCodes[number]; agent_type?: "HISTORY" | "TRANSACTION" | "INVENTORY" | null };
export type NormalizedEvidence = {
  source_ref: string; source_id: string; source_type: "VOC_REVIEW" | "TRANSACTION" | "INVENTORY"; rank: number;
  retrieved_at: string; source_at: string | null; agent_run_id: string; step_name: "history_investigation" | "investigation_fan_in";
  provenance: ("lexical" | "vector" | "hybrid" | "legacy_reference" | "synthetic_operational")[];
  stance: "SUPPORTING" | "CONTRADICTING" | "NEUTRAL";
  observation_code: "RELATED_HISTORY_MATCH" | "REFERENCE_ONLY" | "REFUND_SIGNAL" | "CANCEL_SIGNAL" | "STOCK_SHORTAGE" | "STOCK_ADJUSTMENT";
};
export type Sufficiency = {
  status: "SUFFICIENT" | "INSUFFICIENT" | "CONFLICTING"; policy_version: "history-support-v1";
  evaluated_dimensions: ("SOURCE_COVERAGE" | "OBSERVATION_SUPPORT" | "CONTRADICTION")[];
  supporting_refs: string[]; contradicting_refs: string[]; evidence_gaps: EvidenceGap[];
  reason_codes: ("NO_EVIDENCE" | "INSUFFICIENT_SOURCE_COVERAGE" | "CONFLICTING_EVIDENCE" | "SUFFICIENT_HISTORY_SUPPORT")[];
};
export type RCACandidate = {
  candidate_id: string; code: "REPEATED_HISTORY_SIGNAL"; hypothesis: string; confidence: number;
  supporting_refs: string[]; contradicting_refs: string[]; unresolved_gaps: EvidenceGap[];
  provenance: "HISTORY_HYPOTHESIS_NOT_CONFIRMED"; generated_by: "DETERMINISTIC" | "LLM_GATEWAY";
  config_version: number; jev_decision_id: string; llm_request_id: string | null;
};
export type EvidenceTrace = { normalized_evidence: NormalizedEvidence[]; sufficiency: Sufficiency | null; rca_candidates: RCACandidate[] };
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.length <= 20 && v.every((s) => typeof s === "string");
const refs = (v: unknown): v is string[] => strings(v) && v.every((s) => /^(review|transaction|inventory):[A-Za-z0-9_.:-]{1,128}$/.test(s));
const date = (v: unknown) => typeof v === "string" && /(Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const gaps = (v: unknown) => Array.isArray(v) && v.every((g) => object(g) && gapCodes.includes(g.code as EvidenceGap["code"]));
export function decodeEvidenceTrace(v: Record<string, unknown>): EvidenceTrace | null {
  const items = v.normalized_evidence ?? [], sufficiency = v.sufficiency ?? null, candidates = v.rca_candidates ?? [];
  if (!Array.isArray(items) || items.length > 20 || !items.every((e) => object(e) && refs([e.source_ref]) &&
    e.source_ref === `${e.source_type === "VOC_REVIEW" ? "review" : String(e.source_type).toLowerCase()}:${e.source_id}` && ["VOC_REVIEW", "TRANSACTION", "INVENTORY"].includes(String(e.source_type)) && e.agent_run_id === v.agent_run_id && ["history_investigation", "investigation_fan_in"].includes(String(e.step_name)) &&
    Number.isSafeInteger(e.rank) && Number(e.rank) >= 1 && Number(e.rank) <= 20 && date(e.retrieved_at) && (e.source_at === null || date(e.source_at)) &&
    strings(e.provenance) && e.provenance.length > 0 && e.provenance.every((p) => ["lexical", "vector", "hybrid", "legacy_reference", "synthetic_operational"].includes(p)) &&
    ["SUPPORTING", "CONTRADICTING", "NEUTRAL"].includes(String(e.stance)) && ["RELATED_HISTORY_MATCH", "REFERENCE_ONLY", "REFUND_SIGNAL", "CANCEL_SIGNAL", "STOCK_SHORTAGE", "STOCK_ADJUSTMENT"].includes(String(e.observation_code)))) return null;
  const available = new Map((items as NormalizedEvidence[]).map((e) => [e.source_ref, e]));
  const actualRefs = (value: unknown): value is string[] => refs(value) && value.every((r) => available.has(r));
  if (available.size !== items.length) return null;
  if (sufficiency !== null && (!object(sufficiency) || !["SUFFICIENT", "INSUFFICIENT", "CONFLICTING"].includes(String(sufficiency.status)) ||
    sufficiency.policy_version !== "history-support-v1" || !actualRefs(sufficiency.supporting_refs) || !actualRefs(sufficiency.contradicting_refs) ||
    !gaps(sufficiency.evidence_gaps) || !strings(sufficiency.evaluated_dimensions) || !sufficiency.evaluated_dimensions.every((d) => ["SOURCE_COVERAGE", "OBSERVATION_SUPPORT", "CONTRADICTION"].includes(d)) ||
    !strings(sufficiency.reason_codes) || !sufficiency.reason_codes.every((r) => ["NO_EVIDENCE", "INSUFFICIENT_SOURCE_COVERAGE", "CONFLICTING_EVIDENCE", "SUFFICIENT_HISTORY_SUPPORT"].includes(r)))) return null;
  if (!Array.isArray(candidates) || candidates.length > 5 || !candidates.every((c) => object(c) && object(sufficiency) && sufficiency.status === "SUFFICIENT" &&
    typeof c.candidate_id === "string" && c.code === "REPEATED_HISTORY_SIGNAL" && typeof c.hypothesis === "string" && c.hypothesis.length <= 256 &&
    typeof c.confidence === "number" && Number.isFinite(c.confidence) && c.confidence >= 0 && c.confidence <= 1 &&
    actualRefs(c.supporting_refs) && c.supporting_refs.length > 0 && c.supporting_refs.every((r) => available.get(r)?.stance === "SUPPORTING") &&
    actualRefs(c.contradicting_refs) && c.contradicting_refs.every((r) => available.get(r)?.stance === "CONTRADICTING") &&
    !c.supporting_refs.some((r) => (c.contradicting_refs as string[]).includes(r)) && gaps(c.unresolved_gaps) &&
    c.provenance === "HISTORY_HYPOTHESIS_NOT_CONFIRMED" && ["DETERMINISTIC", "LLM_GATEWAY"].includes(String(c.generated_by)) &&
    c.config_version === v.config_version && c.jev_decision_id === v.jev_decision_id && (c.llm_request_id === null || typeof c.llm_request_id === "string"))) return null;
  return { normalized_evidence: items as NormalizedEvidence[], sufficiency: sufficiency as Sufficiency | null, rca_candidates: candidates as RCACandidate[] };
}
