import { apiBaseUrl, apiMode } from "../incidents";
import { authHeaders } from "../auth";
import type { DecisionApi, DecisionHistory, ShadowDecision } from "./types";

export class DecisionApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string) { super(message); this.name = "DecisionApiError"; }
}
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const integer = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
function invalid(): never { throw new DecisionApiError("CONTRACT_ERROR", "판단 기록의 응답 형식이 올바르지 않습니다. 관리자에게 알려 주세요."); }
export function decodeDecision(value: unknown): ShadowDecision {
  if (!object(value) || value.mode !== "SHADOW" || !["COLD_CHAIN_INVESTIGATION", "SUPPLIER_LOT_INVESTIGATION", "HISTORY_RECURRENCE", "TRANSACTION_INVESTIGATION", "GENERAL_INVESTIGATION", "MANUAL_REVIEW"].includes(String(value.route)) ||
    !["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(String(value.risk_level)) || !["P1", "P2", "P3"].includes(String(value.priority)) ||
    !["decision_id", "incident_id", "source_job_id", "workflow_profile", "budget_profile", "ruleset_version"].every((key) => typeof value[key] === "string" && value[key] !== "") ||
    !Array.isArray(value.investigation_agents) || !value.investigation_agents.every((item) => ["TEMPERATURE", "INVENTORY", "LOT", "SUPPLIER", "HISTORY", "TRANSACTION"].includes(item)) ||
    !Array.isArray(value.reason_codes) || !value.reason_codes.every((item) => typeof item === "string") ||
    typeof value.requires_llm !== "boolean" || typeof value.requires_human_review !== "boolean" || !integer(value.config_version) || !integer(value.incident_version) ||
    typeof value.duration_ms !== "number" || !Number.isFinite(value.duration_ms) || value.duration_ms < 0 ||
    typeof value.decided_at !== "string" || !/(Z|[+-]\d{2}:\d{2})$/.test(value.decided_at) || !Number.isFinite(Date.parse(value.decided_at)) ||
    (value.manual_reason !== null && typeof value.manual_reason !== "string") || (value.error_code !== null && typeof value.error_code !== "string")) invalid();
  return value as unknown as ShadowDecision;
}
export function createHttpDecisionApi(baseUrl: string, transport: typeof fetch = fetch): DecisionApi {
  async function query(path: string): Promise<unknown> {
    let response: Response;
    try { response = await transport(`${baseUrl.replace(/\/$/, "")}${path}`, { headers: authHeaders() }); }
    catch { throw new DecisionApiError("NETWORK_ERROR", "판단 기록 서버에 연결할 수 없습니다. 연결을 확인하고 다시 불러와 주세요."); }
    const requestId = response.headers.get("X-Request-ID") ?? undefined;
    if (!response.ok) {
      let body: unknown;
      try { body = await response.json(); } catch { body = undefined; }
      const code = object(body) && object(body.error) && typeof body.error.code === "string" ? body.error.code : "HTTP_ERROR";
      const id = object(body) && typeof body.request_id === "string" ? body.request_id : requestId;
      const message = response.status === 401 ? "로그인이 필요합니다. 인증 설정을 확인해 주세요." : response.status === 403 ? "현재 계정은 이 매장의 판단 기록을 조회할 권한이 없습니다." : response.status === 404 ? "인시던트를 찾을 수 없거나 접근할 수 없습니다." : "현재 판단 기록을 조회할 수 없습니다. 잠시 후 다시 불러와 주세요.";
      throw new DecisionApiError(code, `${message}${id ? ` · 요청 ID: ${id}` : ""}`, id);
    }
    try { return await response.json(); } catch { invalid(); }
  }
  return {
    async latest(id) { const value = await query(`/incidents/${encodeURIComponent(id)}/decisions/latest`); return value === null ? null : decodeDecision(value); },
    async history(id, limit = 20, offset = 0): Promise<DecisionHistory> {
      const value = await query(`/incidents/${encodeURIComponent(id)}/decisions?limit=${limit}&offset=${offset}`);
      if (!object(value) || !Array.isArray(value.decisions) || value.limit !== limit || value.offset !== offset || typeof value.has_more !== "boolean" || value.decisions.length > limit) invalid();
      return { decisions: value.decisions.map(decodeDecision), limit, offset, has_more: value.has_more };
    },
  };
}
// 예시 모드에서는 실제 실행 기록을 만들어 표시하지 않습니다.
export const mockDecisionApi: DecisionApi = { async latest() { return null; }, async history(_id, limit = 20, offset = 0) { return { decisions: [], limit, offset, has_more: false }; } };
export const decisionApi = apiMode === "http" ? createHttpDecisionApi(apiBaseUrl) : mockDecisionApi;
