import { apiBaseUrl, authHeaders } from "../../shared/api";

export type ValidationScenario = "happy_path" | "more_evidence" | "reopen" | "manual_takeover" | "abandon";
export type Milestone = "ONBOARDING_STARTED" | "DATA_READY" | "INCIDENT_OPENED" | "AI_BRIEF_VIEWED" | "EVIDENCE_REVIEWED" | "HUMAN_ACTION_PRESENTED" | "REVIEW_OPENED" | "DECISION_SUBMITTED" | "VERIFICATION_VIEWED" | "FINAL_STATUS_VIEWED" | "FEEDBACK_SUBMITTED";
export type Friction = "BACKTRACK" | "REPEATED_ACTION" | "HELP_OPENED" | "EXPLANATION_EXPANDED" | "MANUAL_TAKEOVER" | "ACTION_REJECTED" | "REQUEST_MORE_EVIDENCE" | "TASK_ABANDONED" | "ERROR_RECOVERED" | "NO_CLEAR_NEXT_ACTION";
export type FeedbackDecision = "ACCEPT" | "EDIT" | "REJECT" | "REQUEST_MORE_EVIDENCE" | "MANUAL_TAKEOVER";
export type ValidationSignal = { milestone?: Milestone; friction?: Friction; feedback_decision?: FeedbackDecision; artifact_type?: "RCA" | "CAPA" | "INCIDENT"; surface: "ONBOARDING" | "DASHBOARD" | "INCIDENT" | "EVIDENCE" | "REVIEW" | "VERIFICATION" | "EXPLANATION"; incident_id?: string; safe_reason_code?: "NOT_CLEAR" | "DATA_MISSING" | "PERMISSION" | "NETWORK" | "NEEDS_REVIEW" | "USER_CHOICE" };
export type ValidationSession = { session_id: string; store_id: string; scenario_id: ValidationScenario; status: "ACTIVE" | "COMPLETED" | "ABANDONED"; validation_kind: "SYNTHETIC" | "USER_OBSERVATION"; incident_id: string | null; agent_run_id: string | null };
export type ValidationView = { session: ValidationSession; task: { business_goal: string }; journey: { task_success: boolean; incident_status: string | null; milestones: { milestone: Milestone; occurred_at: string }[] }; event_limit_reached: boolean };

export async function validationRequest(path: string, method = "GET", body?: unknown, key?: string): Promise<unknown> {
  let response: Response;
  try { response = await fetch(`${apiBaseUrl}/validation${path}`, { method, headers: { ...authHeaders(), "Content-Type": "application/json", ...(key ? { "Idempotency-Key": key } : {}) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) }); }
  catch { throw new Error("사용자 검증 서버에 연결하지 못했습니다. 다시 시도해 주세요."); }
  if (!response.ok) throw new Error(response.status === 403 ? "이 매장 또는 검증 기록에 접근할 권한이 없습니다." : response.status === 404 ? "검증 기록을 찾을 수 없습니다." : response.status === 409 ? "현재 업무 상태에서는 완료하거나 기록할 수 없습니다. 실제 결과를 먼저 확인해 주세요." : `검증 요청을 처리하지 못했습니다 (${response.status}). 다시 시도해 주세요.`);
  try { return await response.json(); } catch { throw new Error("검증 응답 형식을 확인해 주세요."); }
}
export function decodeValidation(value: unknown): ValidationView {
  const v = value as ValidationView;
  if (!v || typeof v.session?.session_id !== "string" || !["ACTIVE", "COMPLETED", "ABANDONED"].includes(v.session.status) || !["SYNTHETIC", "USER_OBSERVATION"].includes(v.session.validation_kind) || typeof v.task?.business_goal !== "string" || typeof v.journey?.task_success !== "boolean" || !Array.isArray(v.journey.milestones) || v.journey.milestones.length > 11 || typeof v.event_limit_reached !== "boolean") throw new Error("검증 응답 형식을 확인해 주세요.");
  return v;
}
export const validationApi = {
  async get(id: string) { return decodeValidation(await validationRequest(`/sessions/${encodeURIComponent(id)}`)); },
  async start(store: string, scenario: ValidationScenario, key: string) {
    const value = await validationRequest("/sessions", "POST", { store, scenario_id: scenario, consent: true }, key) as ValidationSession;
    if (typeof value?.session_id !== "string") throw new Error("검증 시작 응답을 확인해 주세요.");
    return value;
  },
  async signal(id: string, body: ValidationSignal, key: string) { await validationRequest(`/sessions/${encodeURIComponent(id)}/events`, "POST", body, key); },
  async finish(id: string, key: string) { await validationRequest(`/sessions/${encodeURIComponent(id)}/complete`, "POST", {}, key); },
};
