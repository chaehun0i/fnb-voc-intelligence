import type { DashboardSnapshot } from "../../contracts/types";
import { mockApi } from "../../shared/mockApi";
import { apiBaseUrl, apiMode, authHeaders } from "../../shared/api";

export interface DashboardApi {
  getSnapshot(): Promise<DashboardSnapshot>;
}

// 예시도 하나의 Snapshot 계약을 사용하며 실제 HTTP 경로와 합치지 않습니다.
export const mockDashboardApi: DashboardApi = {
  getSnapshot: () => mockApi.getDashboardSnapshot(),
};

export class DashboardApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string) {
    super(message); this.name = "DashboardApiError";
  }
}
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const count = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const date = (value: unknown) => typeof value === "string" && /(Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
function invalid(): never { throw new DashboardApiError("CONTRACT_ERROR", "운영 현황 응답 형식이 올바르지 않습니다. 관리자에게 알려 주세요."); }

export function decodeDashboard(value: unknown): DashboardSnapshot {
  if (!record(value) || !date(value.as_of) || value.window !== "7d" || value.timezone !== "UTC" || !record(value.kpis) ||
    !["open_incidents", "critical_incidents", "pending_approvals", "failed_jobs", "dlq_jobs", "queue_depth", "running_jobs"].every((key) => count((value.kpis as Record<string, unknown>)[key])) ||
    !Array.isArray(value.incident_trend) || value.incident_trend.length !== 7 ||
    !value.incident_trend.every((item) => record(item) && typeof item.day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(item.day) && count(item.detected) && count(item.resolved)) ||
    !Array.isArray(value.root_cause_distribution) || !value.root_cause_distribution.every((item) => record(item) && typeof item.label === "string" && count(item.count)) ||
    !Array.isArray(value.capa_status) || value.capa_status.length !== 3 || !value.capa_status.every((item) => record(item) && ["PROPOSED", "APPROVED", "EXECUTED"].includes(String(item.status)) && count(item.count)) ||
    new Set(value.capa_status.map((item) => item.status)).size !== 3 ||
    !record(value.integration_health) || value.integration_health.status !== "NOT_IMPLEMENTED" || typeof value.integration_health.reason !== "string" ||
    !Array.isArray(value.priority_incidents) || value.priority_incidents.length > 4 || !value.priority_incidents.every((item) => record(item) && ["id", "title", "store", "owner"].every((key) => typeof item[key] === "string") && ["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(String(item.severity)))) invalid();
  const asOf = new Date(value.as_of as string);
  const today = Date.UTC(asOf.getUTCFullYear(), asOf.getUTCMonth(), asOf.getUTCDate());
  if (!value.incident_trend.every((item, index) => item.day === new Date(today - (6 - index) * 86400000).toISOString().slice(0, 10))) invalid();
  return value as unknown as DashboardSnapshot;
}

export function createHttpDashboardApi(baseUrl: string, transport: typeof fetch = fetch): DashboardApi {
  return { async getSnapshot() {
    let response: Response;
    try { response = await transport(`${baseUrl.replace(/\/$/, "")}/dashboard?window=7d`, { headers: authHeaders() }); }
    catch { throw new DashboardApiError("NETWORK_ERROR", "서버에 연결할 수 없습니다. 연결을 확인하고 다시 불러와 주세요."); }
    let body: unknown;
    try { body = await response.json(); } catch { invalid(); }
    if (!response.ok) {
      const error = record(body) && record(body.error) ? body.error : {};
      const code = typeof error.code === "string" ? error.code : "HTTP_ERROR";
      const requestId = record(body) && typeof body.request_id === "string" ? body.request_id : response.headers.get("X-Request-ID") ?? undefined;
      const message = response.status === 401 ? "로그인이 필요합니다. 인증 설정을 확인해 주세요." : response.status === 403 ? "현재 역할에서는 운영 현황을 조회할 수 없습니다." : "현재 운영 현황을 조회할 수 없습니다. 잠시 후 다시 불러와 주세요.";
      throw new DashboardApiError(code, `${message}${requestId ? ` (요청 ID: ${requestId})` : ""}`, requestId);
    }
    return decodeDashboard(body);
  } };
}

export const dashboardApi = apiMode === "http" ? createHttpDashboardApi(apiBaseUrl) : mockDashboardApi;
