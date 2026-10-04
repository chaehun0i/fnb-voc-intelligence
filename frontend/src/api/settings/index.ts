import { mockApi } from "../mockApi";
import { apiBaseUrl, apiMode } from "../incidents";
import { authHeaders } from "../auth";
import type { ConfigWorkspace, ControlPlaneConfig } from "../../contracts/types";
import type { RuntimeConfig, RuntimeHistory, RuntimeWorkspace, SettingsApi } from "./types";

export class SettingsApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string, public details: Array<{ field: string; reason?: string }> = []) { super(message); this.name = "SettingsApiError"; }
}
const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string";
const date = (v: unknown) => text(v) && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const integer = (v: unknown) => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const booleans = ["jev_enabled", "auto_investigation", "auto_rca_draft", "auto_capa_draft", "auto_execute", "separation_of_duties"];
const numbers = ["max_agent_iterations", "max_tool_calls", "parallelism", "timeout_seconds", "token_budget", "gemini_concurrency", "gemini_rate_limit", "gemini_timeout_seconds", "structured_output_retry", "critical_approver_count", "tenant_queue_concurrency", "retry_limit", "backoff_seconds", "verification_window_hours"];
function invalid(): never { throw new SettingsApiError("CONTRACT_ERROR", "운영 설정 응답 형식을 확인할 수 없습니다. API와 화면 버전을 확인해 주세요."); }
export function decodeRuntimeConfig(v: unknown): RuntimeConfig {
  if (!record(v) || !booleans.every((k) => typeof v[k] === "boolean") || !numbers.every((k) => integer(v[k])) ||
    typeof v.cost_budget_usd !== "number" || !Number.isFinite(v.cost_budget_usd) || v.cost_budget_usd < 0 ||
    !["gemini", "ollama"].includes(String(v.default_llm_provider)) || !["gemini", "ollama"].includes(String(v.fallback_llm_provider)) || v.priority_policy !== "STRICT_PRIORITY" ||
    !record(v.approval_policy_by_risk) || !["LOW", "MEDIUM", "HIGH", "CRITICAL"].every((k) => typeof (v.approval_policy_by_risk as Record<string, unknown>)[k] === "boolean") ||
    !["required_roles", "allowed_tools"].every((k) => Array.isArray(v[k]) && (v[k] as unknown[]).every(text))) invalid();
  return v as unknown as RuntimeConfig;
}
export function decodeWorkspace(v: unknown): RuntimeWorkspace {
  if (!record(v) || !record(v.config) || !integer(v.config.version) || !record(v.sources) || !record(v.rules) ||
    !Array.isArray(v.adjusted_fields) || !v.adjusted_fields.every(text) || v.runtime_status !== "NOT_CONNECTED" || v.scope !== "TENANT" || !record(v.current)) invalid();
  decodeRuntimeConfig(v.config); const effective = decodeRuntimeConfig(v.effective);
  if (!Object.keys(effective).every((k) => ["TENANT", "PLATFORM_DEFAULT"].includes(String((v.sources as Record<string, unknown>)[k]))) ||
    !(v.current.created_at === null || date(v.current.created_at)) || !(v.current.created_by === null || text(v.current.created_by)) ||
    !text(v.current.reason) || !(v.current.parent_version === null || integer(v.current.parent_version))) invalid();
  for (const p of [v.save_permission, v.rollback_permission]) if (!record(p) || typeof p.allowed !== "boolean" || !text(p.reason)) invalid();
  for (const r of Object.values(v.rules)) if (!record(r) || typeof r.min !== "number" || !Number.isFinite(r.min) || typeof r.max !== "number" || !Number.isFinite(r.max) || r.min > r.max || typeof r.integer !== "boolean") invalid();
  return v as unknown as RuntimeWorkspace;
}
export function decodeHistory(v: unknown): RuntimeHistory {
  if (!record(v) || !Array.isArray(v.revisions) || !integer(v.limit) || Number(v.limit) < 1 || Number(v.limit) > 100 || !integer(v.offset) || typeof v.has_more !== "boolean") invalid();
  for (const r of v.revisions) {
    if (!record(r) || !integer(r.version) || Number(r.version) < 1 || !date(r.created_at) || !text(r.actor) || !text(r.reason) ||
      !(r.parent_version === null || integer(r.parent_version)) || !(r.rollback_source === null || integer(r.rollback_source)) || !Array.isArray(r.changes) ||
      !r.changes.every((c) => record(c) && text(c.field) && text(c.before) && text(c.after))) invalid();
    decodeRuntimeConfig(r.snapshot);
  }
  return v as unknown as RuntimeHistory;
}

export function createHttpSettingsApi(baseUrl: string, fetcher: typeof fetch = fetch): SettingsApi {
  async function request(path: string, body?: object, key?: string): Promise<unknown> {
    let response: Response;
    try { response = await fetcher(`${baseUrl.replace(/\/+$/, "")}/settings/runtime${path}`, { method: body ? "POST" : "GET", headers: { Accept: "application/json", ...authHeaders(), ...(body ? { "Content-Type": "application/json", "Idempotency-Key": key! } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) }); }
    catch { throw new SettingsApiError("NETWORK_ERROR", "서버에 연결하지 못했습니다. 같은 입력으로 다시 시도하면 요청 키를 유지합니다."); }
    let payload: unknown;
    try { payload = await response.json(); } catch { throw new SettingsApiError(response.ok ? "CONTRACT_ERROR" : "HTTP_ERROR", "서버 응답을 읽지 못했습니다.", response.headers.get("X-Request-ID") ?? undefined); }
    if (!response.ok) {
      const error = record(payload) && record(payload.error) ? payload.error : undefined;
      const code = error && text(error.code) ? error.code : `HTTP_${response.status}`;
      const messages: Record<string, string> = { AUTHENTICATION_REQUIRED: "로그인이 필요합니다. 인증 설정을 확인해 주세요.", INVALID_CREDENTIALS: "인증 정보가 유효하지 않습니다.", AUTHORIZATION_DENIED: "조직 운영 설정을 변경하려면 HQ_ADMIN 권한이 필요합니다.", VERSION_CONFLICT: "다른 운영자가 설정을 변경했습니다. 최신 설정을 다시 불러와 주세요.", IDEMPOTENCY_CONFLICT: "같은 요청 키에 다른 내용이 전달되었습니다. 최신 설정을 확인해 주세요.", CONFIG_VALIDATION_FAILED: "설정의 안전 범위와 승인 정책을 확인해 주세요.", VALIDATION_ERROR: "필수 입력과 필드 형식을 확인해 주세요.", NOT_FOUND: "현재 조직에서 해당 설정 버전을 찾을 수 없습니다.", SETTINGS_UNAVAILABLE: "운영 설정 저장소를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.", PROCESSING: "요청을 처리 중입니다. 잠시 후 같은 입력으로 다시 시도해 주세요." };
      const details = error && Array.isArray(error.details) ? error.details.filter((d) => record(d) && text(d.field)).map((d) => ({ field: String(d.field), ...(text(d.reason) ? { reason: d.reason } : {}) })) : [];
      throw new SettingsApiError(code, messages[code] ?? "운영 설정 요청을 처리하지 못했습니다.", record(payload) && text(payload.request_id) ? payload.request_id : response.headers.get("X-Request-ID") ?? undefined, details);
    }
    return payload;
  }
  return {
    current: async () => decodeWorkspace(await request("")),
    history: async (limit = 20, offset = 0) => decodeHistory(await request(`/history?limit=${limit}&offset=${offset}`)),
    save: async (config, expectedVersion, reason, key) => decodeWorkspace(await request("", { config, expected_version: expectedVersion, reason }, key)),
    rollback: async (targetVersion, expectedVersion, reason, key) => decodeWorkspace(await request("/rollback", { target_version: targetVersion, expected_version: expectedVersion, reason }, key)),
  };
}

function previewConfig(config: ControlPlaneConfig): RuntimeConfig {
  const { version: _version, ...raw } = config; void _version;
  return { structured_output_retry: 2, required_roles: ["HQ_ADMIN", "REVIEWER"], separation_of_duties: true, critical_approver_count: 2, priority_policy: "STRICT_PRIORITY", backoff_seconds: 2, allowed_tools: [], verification_window_hours: 24, ...raw };
}
function previewWorkspace(w: ConfigWorkspace): RuntimeWorkspace {
  const raw = previewConfig(w.config);
  return { config: { ...raw, version: w.config.version }, effective: raw, sources: Object.fromEntries(Object.keys(raw).map((k) => [k, "TENANT"])), adjusted_fields: [], current: { created_at: w.revisions[0]?.created_at ?? null, created_by: w.revisions[0]?.actor ?? null, reason: w.revisions[0]?.reason ?? "미리보기", parent_version: w.config.version > 1 ? w.config.version - 1 : null }, runtime_status: "NOT_CONNECTED", rules: w.rules as RuntimeWorkspace["rules"], save_permission: w.save_permission, rollback_permission: w.rollback_permission, scope: "TENANT" };
}
export const mockSettingsApi: SettingsApi = {
  current: async () => previewWorkspace(await mockApi.getConfigWorkspace()),
  history: async (limit = 20, offset = 0) => {
    const w = await mockApi.getConfigWorkspace();
    return { revisions: w.revisions.slice(offset, offset + limit).map((r) => ({ ...r, parent_version: r.version > 1 ? r.version - 1 : null, rollback_source: null, snapshot: previewConfig(r.snapshot) })), limit, offset, has_more: w.revisions.length > offset + limit };
  },
  save: async (config, expectedVersion, reason) => previewWorkspace(await mockApi.saveConfig({ ...config, version: expectedVersion } as ControlPlaneConfig, reason)),
  rollback: async (targetVersion, _expectedVersion, reason) => previewWorkspace(await mockApi.rollbackConfig(targetVersion, reason)),
};
export const settingsApi = apiMode === "http" ? createHttpSettingsApi(apiBaseUrl) : mockSettingsApi;
