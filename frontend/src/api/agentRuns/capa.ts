// Proposal은 외부 실행 명령이 아닙니다. 최종 위험/승인 정책은 서버가 계산합니다.
export type CAPAProposal = {
  capa_proposal_id: string; incident_id: string; agent_run_id: string; rca_candidate_id: string;
  summary: string; risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  expected_effect: string; verification_criteria: string; supporting_evidence_ids: string[];
  required_approval: boolean; proposed_action_type: "MANUAL_HISTORY_REVIEW"; target_reference: string;
  assumptions: string[]; uncertainties: string[]; config_version: number; decision_reference: string;
  status: "PROPOSED" | "APPLIED";
};

export type ApprovalTrace = {
  approval_id: string; action_ids: string[]; action_digest: string; config_version: number; incident_version: number;
  status: "PENDING" | "APPROVED" | "REJECTED"; phase: "WAITING_APPROVAL" | "READY_TO_EXECUTE" | "REJECTED";
  waiting_since: string; resumed_at: string | null; decision_actor: string | null;
  decision_reason_code: "HUMAN_APPROVED" | "HUMAN_REJECTED" | null;
};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.length <= 20 && v.every((s) => typeof s === "string" && s.length > 0 && s.length <= 256);
const text = (v: unknown) => typeof v === "string" && v.length > 0 && v.length <= 256;
const date = (v: unknown) => typeof v === "string" && /(Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
export function decodeCAPATrace(run: Record<string, unknown>): { capa_proposals: CAPAProposal[]; approval: ApprovalTrace | null } | null {
  const proposals = run.capa_proposals ?? [], approval = run.approval ?? null;
  const rcas = Array.isArray(run.rca_candidates) ? run.rca_candidates : [];
  if (!Array.isArray(proposals) || proposals.length > 3 || !proposals.every((p) => object(p) &&
    ["capa_proposal_id", "summary", "expected_effect", "verification_criteria", "rca_candidate_id"].every((k) => text(p[k])) &&
    p.incident_id === run.incident_id && p.agent_run_id === run.agent_run_id && p.config_version === run.config_version && p.decision_reference === run.jev_decision_id &&
    ["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(String(p.risk_level)) && typeof p.required_approval === "boolean" &&
    p.proposed_action_type === "MANUAL_HISTORY_REVIEW" && p.target_reference === run.incident_id && ["PROPOSED", "APPLIED"].includes(String(p.status)) &&
    strings(p.supporting_evidence_ids) && p.supporting_evidence_ids.length > 0 &&
    rcas.some((r) => object(r) && r.candidate_id === p.rca_candidate_id && strings(r.supporting_refs) &&
      (p.supporting_evidence_ids as string[]).every((id) => (r.supporting_refs as string[]).includes(id))) && strings(p.assumptions) && strings(p.uncertainties))) return null;
  if (approval !== null && (!object(approval) || !text(approval.approval_id) || !strings(approval.action_ids) || !approval.action_ids.length ||
    approval.action_ids.length !== proposals.length || !approval.action_ids.every((id) => proposals.some((p) => p.capa_proposal_id === id && p.status === "APPLIED")) ||
    typeof approval.action_digest !== "string" || !/^[a-f0-9]{64}$/.test(approval.action_digest) || approval.config_version !== run.config_version ||
    !Number.isSafeInteger(approval.incident_version) || Number(approval.incident_version) < 1 ||
    !["PENDING", "APPROVED", "REJECTED"].includes(String(approval.status)) || !["WAITING_APPROVAL", "READY_TO_EXECUTE", "REJECTED"].includes(String(approval.phase)) ||
    !date(approval.waiting_since) || (approval.resumed_at !== null && !date(approval.resumed_at)) ||
    (approval.decision_actor !== null && !text(approval.decision_actor)) || ![null, "HUMAN_APPROVED", "HUMAN_REJECTED"].includes(approval.decision_reason_code as null))) return null;
  return { capa_proposals: proposals as CAPAProposal[], approval: approval as ApprovalTrace | null };
}
