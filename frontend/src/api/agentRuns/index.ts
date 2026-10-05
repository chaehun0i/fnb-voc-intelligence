import { authHeaders } from "../auth";
import { apiBaseUrl, apiMode } from "../incidents";

export type HistoryRun = {
  agent_run_id: string; incident_id: string; workflow_id: string; job_id: string;
  correlation_id: string; config_version: number; jev_decision_id: string; workflow_version: "history-v1";
  status: "RUNNING" | "COMPLETED" | "FAILED"; started_at: string; completed_at: string | null;
  error_code: "WORKFLOW_FAILED" | null; safe_error_summary: string | null; route: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"; token_spent: number; cost_spent: number;
  iteration: number; tool_call_count: number;
  findings: { code: "RELATED_HISTORY_FOUND"; evidence_refs: string[] }[];
  evidence_candidates: { source_ref: string; source_type: "VOC_REVIEW"; rank: number; retrieved_at: string }[];
  evidence_gaps: { code: "NO_AUTHORIZED_HISTORY" | "LLM_POLICY_DENIED" | "LLM_UNAVAILABLE" }[];
};
export type HistoryStep = { agent_run_id: string; sequence: number; node_name: "validate_context" | "history_investigation" | "persist_result"; attempt: number; status: HistoryRun["status"]; started_at: string; completed_at: string; latency_ms: number; token_spent: number; cost_spent: number; evidence_refs: string[]; error_code: string | null };
export type HistoryRunDetail = HistoryRun & { steps: HistoryStep[] };
export type HistoryRunPage = { runs: HistoryRun[]; limit: number; offset: number; has_more: boolean };
export type AgentRunApi = { list(id: string): Promise<HistoryRunPage>; detail(id: string, runId: string): Promise<HistoryRunDetail> };

export class AgentRunApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string) { super(message); this.name = "AgentRunApiError"; }
}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown) => typeof v === "string" && v.length > 0;
const number = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v >= 0;
const integer = (v: unknown) => number(v) && Number.isSafeInteger(v);
const date = (v: unknown) => typeof v === "string" && /(Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const refs = (v: unknown) => Array.isArray(v) && v.length <= 20 && v.every((r) => typeof r === "string" && /^review:[A-Za-z0-9_.:-]{1,128}$/.test(r));
const status = (v: unknown) => ["RUNNING", "COMPLETED", "FAILED"].includes(String(v));
function invalid(): never { throw new AgentRunApiError("CONTRACT_ERROR", "실행 이력의 응답 형식이 올바르지 않습니다. API 버전을 확인해 주세요."); }
export function decodeRun(v: unknown): HistoryRun {
  if (!object(v) || !["agent_run_id", "incident_id", "workflow_id", "job_id", "correlation_id", "jev_decision_id"].every((f) => text(v[f])) ||
    v.workflow_version !== "history-v1" || !status(v.status) || !integer(v.config_version) || Number(v.config_version) < 1 ||
    !date(v.started_at) || (v.completed_at !== null && !date(v.completed_at)) ||
    ![null, "WORKFLOW_FAILED"].includes(v.error_code as null) || (v.safe_error_summary !== null && !text(v.safe_error_summary)) ||
    !["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(String(v.risk_level)) || !text(v.route) ||
    !["token_spent", "iteration", "tool_call_count"].every((f) => integer(v[f])) || !number(v.cost_spent) ||
    !Array.isArray(v.findings) || !v.findings.every((f) => object(f) && f.code === "RELATED_HISTORY_FOUND" && refs(f.evidence_refs)) ||
    !Array.isArray(v.evidence_candidates) || v.evidence_candidates.length > 20 || !v.evidence_candidates.every((e) => object(e) && refs([e.source_ref]) && e.source_type === "VOC_REVIEW" && integer(e.rank) && Number(e.rank) > 0 && date(e.retrieved_at)) ||
    !Array.isArray(v.evidence_gaps) || !v.evidence_gaps.every((g) => object(g) && ["NO_AUTHORIZED_HISTORY", "LLM_POLICY_DENIED", "LLM_UNAVAILABLE"].includes(String(g.code)))) invalid();
  return v as unknown as HistoryRun;
}
export function decodeDetail(v: unknown): HistoryRunDetail {
  const run = decodeRun(v);
  if (!object(v) || !Array.isArray(v.steps) || v.steps.length > 100 || !v.steps.every((s) => object(s) && s.agent_run_id === run.agent_run_id &&
    ["validate_context", "history_investigation", "persist_result"].includes(String(s.node_name)) && integer(s.sequence) && Number(s.sequence) >= 1 && Number(s.sequence) <= 3 &&
    integer(s.attempt) && Number(s.attempt) > 0 && status(s.status) && date(s.started_at) && date(s.completed_at) && number(s.latency_ms) &&
    integer(s.token_spent) && number(s.cost_spent) && refs(s.evidence_refs) && (s.error_code === null || s.error_code === "WORKFLOW_FAILED"))) invalid();
  return { ...run, steps: v.steps as HistoryStep[] };
}
export function createHttpAgentRunApi(baseUrl: string, transport: typeof fetch = fetch): AgentRunApi {
  async function query(path: string): Promise<unknown> {
    let response: Response;
    try { response = await transport(`${baseUrl.replace(/\/$/, "")}${path}`, { headers: authHeaders() }); }
    catch { throw new AgentRunApiError("NETWORK_ERROR", "조사 기록 서버에 연결할 수 없습니다. 연결을 확인해 주세요."); }
    const requestId = response.headers.get("X-Request-ID") ?? undefined;
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const code = object(body) && object(body.error) && typeof body.error.code === "string" ? body.error.code : "HTTP_ERROR";
      const id = object(body) && typeof body.request_id === "string" ? body.request_id : requestId;
      const message = response.status === 401 ? "로그인이 필요합니다." : response.status === 403 ? "현재 계정은 이 매장의 조사 기록을 조회할 권한이 없습니다." : response.status === 404 ? "조사 기록을 찾을 수 없거나 접근할 수 없습니다." : "현재 조사 기록을 조회할 수 없습니다. 잠시 후 다시 불러와 주세요.";
      throw new AgentRunApiError(code, `${message}${id ? ` · 요청 ID: ${id}` : ""}`, id);
    }
    try { return await response.json(); } catch { invalid(); }
  }
  return {
    async list(id) {
      const v = await query(`/incidents/${encodeURIComponent(id)}/agent-runs`);
      if (!object(v) || !Array.isArray(v.runs) || v.limit !== 20 || v.offset !== 0 || typeof v.has_more !== "boolean" || v.runs.length > 20) invalid();
      return { runs: v.runs.map(decodeRun), limit: 20, offset: 0, has_more: v.has_more };
    },
    async detail(id, runId) { return decodeDetail(await query(`/incidents/${encodeURIComponent(id)}/agent-runs/${encodeURIComponent(runId)}`)); },
  };
}
// 예시 Multi-Agent와 실제 History 기록을 섞지 않습니다.
export const mockAgentRunApi: AgentRunApi = { async list() { return { runs: [], limit: 20, offset: 0, has_more: false }; }, async detail() { throw new AgentRunApiError("NOT_FOUND", "예시 모드에는 실제 조사 기록이 없습니다."); } };
export const agentRunApi = apiMode === "http" ? createHttpAgentRunApi(apiBaseUrl) : mockAgentRunApi;
