import { apiBaseUrl, authHeaders } from "../../shared/api";
import type { RuntimeAX } from "./api";

type Dimension = "HISTORY" | "TRANSACTION" | "INVENTORY";
export type IncidentAX = {
  feedback_allowed?: boolean;
  metrics?: { name: string; status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE"; value: number | null; unit: string }[];
  runtime?: RuntimeAX | null;
  schema_version: "incident-ax-1"; incident_id: string; current_phase: string;
  brief: { headline: string; summary: string; primary_hypothesis: string | null; confidence_level: "LOW" | "MEDIUM" | "INCONCLUSIVE" };
  coverage: { confirmed: Dimension[]; missing: Dimension[]; conflicting: Dimension[]; stale: Dimension[]; evidence_count: number };
  uncertainties: string[]; human_action: string;
  next_action: { action_type: string; label: string; reason: string; risk: string; permission: boolean;
    requires_approval: boolean; blocking_reason: string | null; alternative_actions: string[] };
  progress: { agent_type: Dimension; label: string; status: "RUNNING" | "SUCCESS" | "FAILED" | "UNAVAILABLE" | "NO_EVIDENCE" | "STALE"; evidence_count: number }[];
  verification_result: "PASS" | "FAIL" | "INCONCLUSIVE" | null; execution_mode: "INTERNAL_RECORD_ONLY" | null;
  approval_status: "PENDING" | "APPROVED" | "REJECTED" | null; source_run_id: string | null;
  manifest_reference: string | null; decision_reference: string | null;
  explanation: { supporting_refs: string[]; contradicting_refs: string[]; missing_codes: string[];
    assumptions: string[]; cannot_verify: string[]; technical_trace_available: boolean };
  updated_at: string;
};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown) => typeof v === "string" && v.length <= 600;
const texts = (v: unknown) => Array.isArray(v) && v.length <= 30 && v.every(text);
const optional = (v: unknown) => v === null || text(v);
const count = (v: unknown) => Number.isSafeInteger(v) && Number(v) >= 0 && Number(v) <= 20;
const dimensions = ["HISTORY", "TRANSACTION", "INVENTORY"];
const actions = ["NONE", "OPEN_REVIEW", "COLLECT_EVIDENCE", "MANUAL_REVIEW", "CHECK_RESULT", "VERIFY", "OPEN_WORKSPACE"];
export function decodeAX(v: unknown): IncidentAX {
  function invalid(): never { throw new Error("업무 요약 응답 형식이 올바르지 않습니다."); }
  if (!object(v) || v.schema_version !== "incident-ax-1" || !text(v.incident_id) || !text(v.current_phase) ||
    !text(v.updated_at) || !Number.isFinite(Date.parse(String(v.updated_at))) || !texts(v.uncertainties) ||
    !["NONE", "REVIEW_REQUIRED", "APPROVAL_REQUIRED", "MORE_EVIDENCE_REQUIRED", "MANUAL_TAKEOVER_RECOMMENDED", "POLICY_BLOCKED", "BUDGET_INCREASE_REQUIRED", "VERIFICATION_REQUIRED"].includes(String(v.human_action))) invalid();
  const b = v.brief, c = v.coverage, n = v.next_action, e = v.explanation;
  if (v.feedback_allowed !== undefined && typeof v.feedback_allowed !== "boolean") invalid();
  if (v.metrics !== undefined && (!Array.isArray(v.metrics) || v.metrics.length > 7 || !v.metrics.every((m) => object(m) && text(m.name) && ["AVAILABLE", "PARTIAL", "UNAVAILABLE"].includes(String(m.status)) && (m.value === null || typeof m.value === "number" && Number.isFinite(m.value) && m.value >= 0) && text(m.unit)))) invalid();
  if (v.runtime !== undefined && v.runtime !== null) {
    const r = v.runtime;
    if (!object(r) || !["RUNNING", "PAUSED", "STOPPED", "MANUAL_TAKEOVER"].includes(String(r.control_status)) || !Number.isSafeInteger(r.control_version) || Number(r.control_version) < 0 || !optional(r.termination_reason) ||
      ![r.message, r.budget_summary, r.human_action].every(text) || typeof r.new_evidence !== "boolean" || !Number.isSafeInteger(r.remaining_operations) || Number(r.remaining_operations) < 0 ||
      !object(r.permissions) || !["pause", "resume", "stop", "takeover"].every((key) => typeof (r.permissions as Record<string, unknown>)[key] === "boolean") || !object(r.versions) || !Object.values(r.versions).every(text)) invalid();
  }
  if (!object(b) || !text(b.headline) || !text(b.summary) || !optional(b.primary_hypothesis) || !["LOW", "MEDIUM", "INCONCLUSIVE"].includes(String(b.confidence_level)) ||
    !object(c) || !count(c.evidence_count) || !["confirmed", "missing", "conflicting", "stale"].every((key) => texts(c[key]) && (c[key] as string[]).every((d) => dimensions.includes(d))) ||
    !object(n) || !actions.includes(String(n.action_type)) || !text(n.label) || !text(n.reason) || !["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(String(n.risk)) || typeof n.permission !== "boolean" || typeof n.requires_approval !== "boolean" || !optional(n.blocking_reason) || !texts(n.alternative_actions) ||
    !object(e) || !["supporting_refs", "contradicting_refs", "missing_codes", "assumptions", "cannot_verify"].every((key) => texts(e[key])) || typeof e.technical_trace_available !== "boolean" ||
    !Array.isArray(v.progress) || v.progress.length > 3 || !v.progress.every((p) => object(p) && dimensions.includes(String(p.agent_type)) && text(p.label) && ["RUNNING", "SUCCESS", "FAILED", "UNAVAILABLE", "NO_EVIDENCE", "STALE"].includes(String(p.status)) && count(p.evidence_count)) ||
    ![null, "PASS", "FAIL", "INCONCLUSIVE"].includes(v.verification_result as null) || ![null, "INTERNAL_RECORD_ONLY"].includes(v.execution_mode as null) || ![null, "PENDING", "APPROVED", "REJECTED"].includes(v.approval_status as null) ||
    ![v.source_run_id, v.manifest_reference, v.decision_reference].every(optional)) invalid();
  return v as unknown as IncidentAX;
}
export async function getIncidentAX(id: string, transport: typeof fetch = fetch): Promise<IncidentAX> {
  let response: Response;
  try { response = await transport(`${apiBaseUrl}/incidents/${encodeURIComponent(id)}/ax`, { headers: authHeaders() }); }
  catch { throw new Error("업무 요약 서버에 연결하지 못했습니다. 다시 시도해 주세요."); }
  if (!response.ok) throw new Error(({ 401: "로그인이 필요합니다.", 403: "이 매장의 업무 요약을 조회할 권한이 없습니다.",
    404: "사건을 찾을 수 없거나 접근할 수 없습니다." } as Record<number, string>)[response.status] ?? "업무 요약을 조회하지 못했습니다.");
  return decodeAX(await response.json());
}

export type ProductEventType = "ai_brief_viewed" | "evidence_opened" | "explanation_opened" | "recommendation_accepted" | "recommendation_edited" | "recommendation_rejected";
export async function recordAXEvent(id: string, event_type: ProductEventType, key: string, transport: typeof fetch = fetch) {
  const response = await transport(`${apiBaseUrl}/incidents/${encodeURIComponent(id)}/ax/events`, {
    method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify({ event_type }),
  });
  if (!response.ok) throw new Error("피드백을 기록하지 못했습니다. 다시 시도해 주세요.");
}
