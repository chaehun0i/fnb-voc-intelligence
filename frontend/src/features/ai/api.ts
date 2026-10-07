import { authHeaders, apiBaseUrl, apiMode } from "../../shared/api";
import { decodeEvidenceTrace, gapCodes, type EvidenceGap, type EvidenceTrace } from "./evidence";
import { decodeCAPATrace, type ApprovalTrace, type CAPAProposal } from "./capa";
import { decodeClosedLoop, type ClosedLoopTrace } from "./verification";

export type HistoryRun = {
  tools?: ToolProgress[];
  runtime?: RuntimeAX | null;
  agent_run_id: string; incident_id: string; workflow_id: string; job_id: string;
  correlation_id: string; config_version: number; jev_decision_id: string; workflow_version: "history-v1" | "history-evidence-v2" | "history-capa-v3" | "history-verification-v4" | "multi-investigation-v5";
  status: "RUNNING" | "WAITING_APPROVAL" | "COMPLETED" | "FAILED"; started_at: string; completed_at: string | null;
  error_code: "WORKFLOW_FAILED" | null; safe_error_summary: string | null; route: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"; token_spent: number; cost_spent: number;
  iteration: number; tool_call_count: number;
  findings: { code: "RELATED_HISTORY_FOUND" | "TRANSACTION_SIGNAL_FOUND" | "INVENTORY_SIGNAL_FOUND"; evidence_refs: string[] }[];
  evidence_candidates: { source_ref: string; source_type: "VOC_REVIEW" | "TRANSACTION" | "INVENTORY"; rank: number; retrieved_at: string }[];
  investigation?: InvestigationProgress | null;
  evidence_gaps: EvidenceGap[];
  capa_proposals?: CAPAProposal[]; approval?: ApprovalTrace | null;
} & Partial<EvidenceTrace> & ClosedLoopTrace;
export type ToolProgress = { name: "get_incident" | "search_similar_incidents" | "get_transactions" | "get_inventory";
  version: "1"; status: "COMPLETED" | "FAILED" | "PENDING"; message: string;
  evidence_count: number; error_code: string | null; human_action: string };
export type HistoryStep = { agent_run_id: string; sequence: number; node_name: "validate_context" | "history_investigation" | "normalize_evidence" | "evaluate_sufficiency" | "rca_investigation" | "persist_result" | "capa_proposal" | "apply_capa" | "request_approval" | "approval_interrupt" | "approval_result" | "internal_execution" | "begin_verification" | "verification" | "apply_verification"; attempt: number; status: HistoryRun["status"]; started_at: string; completed_at: string; latency_ms: number; token_spent: number; cost_spent: number; evidence_refs: string[]; error_code: string | null };
export type HistoryRunDetail = HistoryRun & { steps: HistoryStep[] };
export type HistoryRunPage = { runs: HistoryRun[]; limit: number; offset: number; has_more: boolean };
export type ControlAction = "pause" | "resume" | "stop" | "takeover";
export type RuntimeAX = {
  control_status: "RUNNING" | "PAUSED" | "STOPPED" | "MANUAL_TAKEOVER";
  control_version: number; termination_reason: string | null; message: string;
  budget_summary: string; remaining_operations: number; new_evidence: boolean; human_action: string;
  permissions: Record<ControlAction, boolean>; versions: Record<string, string>;
};
export type AgentRunApi = { list(id: string): Promise<HistoryRunPage>; detail(id: string, runId: string): Promise<HistoryRunDetail>;
  control?(id: string, runId: string, action: ControlAction, version: number, key: string): Promise<void> };

export type InvestigationProgress = {
  status: "RUNNING" | "PARTIAL" | "COMPLETED"; evidence_count: number;
  uncertainty: "관측 근거이며 원인 확정은 아닙니다."; updated_at: string;
  agents: { agent_type: "HISTORY" | "TRANSACTION" | "INVENTORY"; business_label: string;
    status: "RUNNING" | "SUCCESS" | "FAILED" | "UNAVAILABLE" | "NO_EVIDENCE" | "STALE";
    evidence_count: number; retryable: boolean; gap_codes: string[]; updated_at: string }[];
  coverage: { dimension: "HISTORY" | "TRANSACTION" | "INVENTORY"; status: "CONFIRMED" | "MISSING" | "CONFLICTING" | "STALE" }[];
};

export class AgentRunApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string) { super(message); this.name = "AgentRunApiError"; }
}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown) => typeof v === "string" && v.length > 0;
const number = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v >= 0;
const integer = (v: unknown) => number(v) && Number.isSafeInteger(v);
const date = (v: unknown) => typeof v === "string" && /(Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const refs = (v: unknown) => Array.isArray(v) && v.length <= 20 && v.every((r) => typeof r === "string" && /^(review|transaction|inventory):[A-Za-z0-9_.:-]{1,128}$/.test(r));
const status = (v: unknown) => ["RUNNING", "WAITING_APPROVAL", "COMPLETED", "FAILED"].includes(String(v));
function invalid(): never { throw new AgentRunApiError("CONTRACT_ERROR", "실행 이력의 응답 형식이 올바르지 않습니다. API 버전을 확인해 주세요."); }
export function decodeRun(v: unknown): HistoryRun {
  if (!object(v) || !["agent_run_id", "incident_id", "workflow_id", "job_id", "correlation_id", "jev_decision_id"].every((f) => text(v[f])) ||
    !["history-v1", "history-evidence-v2", "history-capa-v3", "history-verification-v4", "multi-investigation-v5"].includes(String(v.workflow_version)) || !status(v.status) || !integer(v.config_version) || Number(v.config_version) < 1 ||
    !date(v.started_at) || (v.completed_at !== null && !date(v.completed_at)) ||
    ![null, "WORKFLOW_FAILED"].includes(v.error_code as null) || (v.safe_error_summary !== null && !text(v.safe_error_summary)) ||
    !["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(String(v.risk_level)) || !text(v.route) ||
    !["token_spent", "iteration", "tool_call_count"].every((f) => integer(v[f])) || !number(v.cost_spent) ||
    !Array.isArray(v.findings) || !v.findings.every((f) => object(f) && ["RELATED_HISTORY_FOUND", "TRANSACTION_SIGNAL_FOUND", "INVENTORY_SIGNAL_FOUND"].includes(String(f.code)) && refs(f.evidence_refs)) ||
    !Array.isArray(v.evidence_candidates) || v.evidence_candidates.length > 20 || !v.evidence_candidates.every((e) => object(e) && refs([e.source_ref]) && ["VOC_REVIEW", "TRANSACTION", "INVENTORY"].includes(String(e.source_type)) && integer(e.rank) && Number(e.rank) > 0 && date(e.retrieved_at)) ||
    !Array.isArray(v.evidence_gaps) || !v.evidence_gaps.every((g) => object(g) && gapCodes.includes(g.code as EvidenceGap["code"]))) invalid();
  const trace = decodeEvidenceTrace(v);
  if (v.tools !== undefined && (!Array.isArray(v.tools) || v.tools.length > 50 || !v.tools.every((t) =>
    object(t) && ["get_incident", "search_similar_incidents", "get_transactions", "get_inventory"].includes(String(t.name)) &&
    t.version === "1" && ["COMPLETED", "FAILED", "PENDING"].includes(String(t.status)) && text(t.message) &&
    integer(t.evidence_count) && Number(t.evidence_count) <= 20 && (t.error_code === null || text(t.error_code)) && text(t.human_action)))) invalid();
  if (v.runtime !== undefined && v.runtime !== null) {
    const r = v.runtime;
    if (!object(r) || !["RUNNING", "PAUSED", "STOPPED", "MANUAL_TAKEOVER"].includes(String(r.control_status)) ||
      !integer(r.control_version) || !integer(r.remaining_operations) || typeof r.new_evidence !== "boolean" ||
      !["message", "budget_summary", "human_action"].every((f) => text(r[f])) ||
      !(r.termination_reason === null || ["COMPLETED", "NO_NEW_EVIDENCE", "BUDGET_EXHAUSTED", "ITERATION_LIMIT", "POLICY_DENIED", "PAUSED", "STOPPED", "MANUAL_TAKEOVER", "INCOMPLETE"].includes(String(r.termination_reason))) ||
      !object(r.permissions) || !["pause", "resume", "stop", "takeover"].every((a) => typeof (r.permissions as Record<string, unknown>)[a] === "boolean") ||
      !object(r.versions) || !Object.values(r.versions).every(text)) invalid();
  }
  if (!trace) invalid();
  const capa = decodeCAPATrace({ ...v, ...trace });
  if (!capa) invalid();
  const closedLoop = decodeClosedLoop(v);
  if (!closedLoop) invalid();
  if (v.investigation !== undefined && v.investigation !== null) {
    const p = v.investigation;
    const agents = ["HISTORY", "TRANSACTION", "INVENTORY"];
    if (!object(p) || !["RUNNING", "PARTIAL", "COMPLETED"].includes(String(p.status)) || !integer(p.evidence_count) || Number(p.evidence_count) > 60 || !date(p.updated_at) || p.uncertainty !== "관측 근거이며 원인 확정은 아닙니다." ||
      !Array.isArray(p.agents) || p.agents.length > 3 || !p.agents.every((a) => object(a) && agents.includes(String(a.agent_type)) && ["과거 사례 조사", "거래 내역 조사", "재고 조사"].includes(String(a.business_label)) &&
        ["RUNNING", "SUCCESS", "FAILED", "UNAVAILABLE", "NO_EVIDENCE", "STALE"].includes(String(a.status)) && integer(a.evidence_count) && Number(a.evidence_count) <= 20 && typeof a.retryable === "boolean" && date(a.updated_at) && Array.isArray(a.gap_codes) && a.gap_codes.every((g) => gapCodes.includes(g as EvidenceGap["code"]))) ||
      new Set(p.agents.map((a) => (a as Record<string, unknown>).agent_type)).size !== p.agents.length ||
      !Array.isArray(p.coverage) || p.coverage.length > 3 || !p.coverage.every((c) => object(c) && agents.includes(String(c.dimension)) && ["CONFIRMED", "MISSING", "CONFLICTING", "STALE"].includes(String(c.status)))) invalid();
  }
  return { ...(v as unknown as HistoryRun), ...trace, ...capa, ...closedLoop };
}
export function decodeDetail(v: unknown): HistoryRunDetail {
  const run = decodeRun(v);
  if (!object(v) || !Array.isArray(v.steps) || v.steps.length > 100 || !v.steps.every((s) => object(s) && s.agent_run_id === run.agent_run_id &&
    ["validate_context", "history_investigation", "normalize_evidence", "evaluate_sufficiency", "rca_investigation", "persist_result", "capa_proposal", "apply_capa", "request_approval", "approval_interrupt", "approval_result", "internal_execution", "begin_verification", "verification", "apply_verification"].includes(String(s.node_name)) && integer(s.sequence) && Number(s.sequence) >= 1 && Number(s.sequence) <= 15 &&
    integer(s.attempt) && Number(s.attempt) > 0 && status(s.status) && date(s.started_at) && date(s.completed_at) && number(s.latency_ms) &&
    integer(s.token_spent) && number(s.cost_spent) && refs(s.evidence_refs) && (s.error_code === null || s.error_code === "WORKFLOW_FAILED"))) invalid();
  return { ...run, steps: v.steps as HistoryStep[] };
}
export function createHttpAgentRunApi(baseUrl: string, transport: typeof fetch = fetch): AgentRunApi {
  async function query(path: string, options: RequestInit = {}): Promise<unknown> {
    let response: Response;
    try { response = await transport(`${baseUrl.replace(/\/$/, "")}${path}`, { ...options, headers: { ...authHeaders(), ...options.headers } }); }
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
    async control(id, runId, action, version, key) {
      const value = await query(`/incidents/${encodeURIComponent(id)}/agent-runs/${encodeURIComponent(runId)}/controls/${action}`,
        { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify({ expected_version: version }) });
      if (!object(value) || !["RUNNING", "PAUSED", "STOPPED", "MANUAL_TAKEOVER"].includes(String(value.control_status))) invalid();
    },
  };
}
// 예시 Multi-Agent와 실제 History 기록을 섞지 않습니다.
export const mockAgentRunApi: AgentRunApi = { async list() { return { runs: [], limit: 20, offset: 0, has_more: false }; }, async detail() { throw new AgentRunApiError("NOT_FOUND", "예시 모드에는 실제 조사 기록이 없습니다."); } };
export const agentRunApi = apiMode === "http" ? createHttpAgentRunApi(apiBaseUrl) : mockAgentRunApi;
