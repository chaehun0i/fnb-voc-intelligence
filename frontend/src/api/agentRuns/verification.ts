export type VerificationResult = "PASS" | "FAIL" | "INCONCLUSIVE";
export type ExecutionTrace = {
  execution_id: string; incident_id: string; agent_run_id: string; action_id: string; approval_id: string;
  action_digest: string; execution_mode: "INTERNAL_RECORD_ONLY"; status: "SUCCEEDED";
  started_at: string; completed_at: string; safe_result_summary: string;
  config_version: number; correlation_id: string; incident_version: number;
};
export type VerificationEvidence = {
  evidence_id: string; agent_run_id: string; execution_id: string; action_id: string;
  source_ref: string; source_type: "INTERNAL_REVIEW_RECORD"; observation_mode: "SIMULATED";
  observed_at: string; review_record_present: boolean | null; additional_evidence_refs: string[];
};
export type VerificationTrace = {
  verification_id: string; incident_id: string; action_id: string; execution_id: string;
  criteria: string; evidence_ids: string[]; criterion_results: { code: "REVIEW_RECORD_PRESENT" | "ADDITIONAL_EVIDENCE_LIST"; result: VerificationResult }[];
  result: VerificationResult; confidence: number; summary: string; reason_codes: string[];
  verified_at: string; config_version: number; observation_mode: "SIMULATED";
};
export type ClosedLoopTrace = {
  execution?: ExecutionTrace | null; verification?: VerificationTrace | null;
  verification_evidence?: VerificationEvidence[];
  resulting_incident_status?: "EXECUTING" | "VERIFYING" | "RESOLVED" | "REOPENED" | null;
};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const date = (v: unknown) => text(v) && /(Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const result = (v: unknown) => ["PASS", "FAIL", "INCONCLUSIVE"].includes(String(v));
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.length <= 20 && v.every(text);
// 서버 판정을 계산하지 않고 참조·모드·응답 형식만 검증합니다.
export function decodeClosedLoop(v: Record<string, unknown>): ClosedLoopTrace | null {
  const execution = v.execution ?? null, verification = v.verification ?? null, evidence = v.verification_evidence ?? [];
  const state = v.resulting_incident_status ?? null;
  if (![null, "EXECUTING", "VERIFYING", "RESOLVED", "REOPENED"].includes(state as null)) return null;
  if (execution !== null && (!object(execution) || execution.execution_mode !== "INTERNAL_RECORD_ONLY" || execution.status !== "SUCCEEDED" ||
    !["execution_id", "action_id", "approval_id", "safe_result_summary"].every((k) => text(execution[k])) ||
    execution.incident_id !== v.incident_id || execution.agent_run_id !== v.agent_run_id || execution.config_version !== v.config_version || execution.correlation_id !== v.correlation_id ||
    !date(execution.started_at) || !date(execution.completed_at) || Date.parse(String(execution.completed_at)) < Date.parse(String(execution.started_at)) ||
    !Number.isSafeInteger(execution.incident_version) || Number(execution.incident_version) < 1 || !/^[a-f0-9]{64}$/.test(String(execution.action_digest)) ||
    !object(v.approval) || v.approval.status !== "APPROVED" || execution.approval_id !== v.approval.approval_id || execution.action_digest !== v.approval.action_digest)) return null;
  if (!Array.isArray(evidence) || evidence.length > 20 || !evidence.every((e) => object(e) && object(execution) && text(e.evidence_id) &&
    e.agent_run_id === v.agent_run_id && e.execution_id === execution.execution_id && e.action_id === execution.action_id &&
    e.source_type === "INTERNAL_REVIEW_RECORD" && e.observation_mode === "SIMULATED" && /^internal-review:[a-f0-9-]{36}$/.test(String(e.source_ref)) &&
    date(e.observed_at) && [true, false, null].includes(e.review_record_present as null) && strings(e.additional_evidence_refs) && e.additional_evidence_refs.every((r) => /^review:[A-Za-z0-9_.:-]{1,128}$/.test(r)))) return null;
  if (verification !== null && (!object(verification) || !object(execution) || verification.observation_mode !== "SIMULATED" ||
    verification.incident_id !== v.incident_id || verification.execution_id !== execution.execution_id || verification.action_id !== execution.action_id || verification.config_version !== v.config_version ||
    !text(verification.verification_id) || !text(verification.criteria) || !text(verification.summary) || !result(verification.result) || !date(verification.verified_at) ||
    typeof verification.confidence !== "number" || !Number.isFinite(verification.confidence) || verification.confidence < 0 || verification.confidence > 1 ||
    !strings(verification.evidence_ids) || verification.evidence_ids.some((id) => !evidence.some((e) => object(e) && e.evidence_id === id)) ||
    !Array.isArray(verification.criterion_results) || verification.criterion_results.length !== 2 || !verification.criterion_results.every((c) => object(c) && ["REVIEW_RECORD_PRESENT", "ADDITIONAL_EVIDENCE_LIST"].includes(String(c.code)) && result(c.result)) ||
    !strings(verification.reason_codes) || !verification.reason_codes.every((r) => ["CRITERIA_MET", "CRITERIA_NOT_MET", "EVIDENCE_MISSING", "EVIDENCE_STALE", "EVIDENCE_CONFLICTING", "UNSUPPORTED_CRITERIA"].includes(r)))) return null;
  return { execution, verification, verification_evidence: evidence, resulting_incident_status: state } as ClosedLoopTrace;
}
