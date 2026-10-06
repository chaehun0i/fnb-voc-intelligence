import { authHeaders, apiBaseUrl, apiMode } from "../../shared/api";
import { mockApi } from "../../shared/mockApi";
import type { QueueJob } from "../../contracts/types";

export class JobApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string) { super(message); this.name = "JobApiError"; }
}
export interface JobApi {
  listJobs(): Promise<QueueJob[]>;
  getJob(id: string): Promise<QueueJob | undefined>;
  jobAction(id: string, action: "retry" | "cancel", reason: string, key: string, version?: number): Promise<QueueJob>;
}
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const date = (value: unknown) => typeof value === "string" && Number.isFinite(Date.parse(value));
const text = (value: unknown) => typeof value === "string";
function invalid(): never { throw new JobApiError("CONTRACT_ERROR", "작업 응답 형식이 올바르지 않습니다. API와 화면 버전을 확인해 주세요."); }

export function decodeJob(value: unknown): QueueJob {
  if (!record(value) || !["id", "tenant_id", "type", "correlation_id"].every((key) => text(value[key])) ||
    !["PENDING", "RUNNING", "COMPLETED", "FAILED", "DLQ", "CANCELLED"].includes(String(value.status)) ||
    !["P1", "P2", "P3"].includes(String(value.priority)) || !date(value.queued_at) || !date(value.available_at) ||
    !Number.isInteger(value.attempts) || Number(value.attempts) < 0 || !Number.isInteger(value.max_attempts) || Number(value.max_attempts) < 1 || Number(value.attempts) > Number(value.max_attempts) ||
    !Number.isInteger(value.version) || Number(value.version) < 1 || !Number.isInteger(value.config_version) || Number(value.config_version) < 1 || !record(value.actions)) invalid();
  for (const key of ["started_at", "completed_at", "lease_until"]) if (value[key] !== null && !date(value[key])) invalid();
  for (const key of ["incident_id", "parent_job_id", "error_code", "error_summary"]) if (value[key] !== null && !text(value[key])) invalid();
  for (const key of ["retry", "cancel"]) {
    const permission = (value.actions as Record<string, unknown>)[key];
    if (!record(permission) || typeof permission.allowed !== "boolean" || !text(permission.reason)) invalid();
  }
  const normalized = { ...value };
  for (const key of ["incident_id", "parent_job_id", "error_code", "error_summary", "started_at", "completed_at", "lease_until"]) if (normalized[key] === null) delete normalized[key];
  return normalized as unknown as QueueJob;
}

export function createHttpJobApi(baseUrl: string, fetcher: typeof fetch = fetch): JobApi {
  async function request(path: string, body?: object, key?: string) {
    let response: Response;
    try { response = await fetcher(`${baseUrl.replace(/\/+$/, "")}/jobs${path}`, {
      method: body ? "POST" : "GET", headers: { Accept: "application/json", ...authHeaders(),
        ...(body ? { "Content-Type": "application/json", "Idempotency-Key": key! } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    }); } catch { throw new JobApiError("NETWORK_ERROR", "서버에 연결하지 못했습니다. 같은 내용으로 다시 시도하면 요청 키를 유지합니다."); }
    let payload: unknown;
    try { payload = await response.json(); } catch { throw new JobApiError("CONTRACT_ERROR", "서버 응답을 읽지 못했습니다. 다시 불러와 주세요."); }
    if (!response.ok) {
      const error = record(payload) && record(payload.error) ? payload.error : undefined;
      const code = error && text(error.code) ? String(error.code) : `HTTP_${response.status}`;
      const messages: Record<number, string> = { 401: "인증 설정을 확인해 주세요. 로그인이 필요합니다.", 403: "현재 역할 또는 매장 범위에서는 이 작업을 처리할 수 없습니다.", 404: "작업을 찾을 수 없습니다. 목록을 다시 불러와 주세요.", 409: "작업 상태 또는 요청 내용이 충돌했습니다. 최신 정보를 다시 불러와 주세요." };
      throw new JobApiError(code, error && text(error.message) ? String(error.message) : messages[response.status] ?? "작업 요청을 처리하지 못했습니다.",
        record(payload) && text(payload.request_id) ? String(payload.request_id) : undefined);
    }
    return payload;
  }
  return {
    listJobs: async () => { const payload = await request(""); if (!Array.isArray(payload)) invalid(); return payload.map(decodeJob); },
    getJob: async (id) => decodeJob(await request(`/${encodeURIComponent(id)}`)),
    jobAction: async (id, action, reason, key, version) => {
      if (!reason.trim()) throw new JobApiError("VALIDATION_ERROR", "처리 사유를 입력해 주세요.");
      return decodeJob(await request(`/${encodeURIComponent(id)}/${action}`, { reason: reason.trim(), expected_version: version }, key));
    },
  };
}
export const mockJobApi: JobApi = {
  listJobs: () => mockApi.listJobs(),
  getJob: async (id) => (await mockApi.listJobs()).find((job) => job.id === id),
  jobAction: (id, action) => mockApi.jobAction(id, action),
};
export const jobApi = apiMode === "http" ? createHttpJobApi(apiBaseUrl) : mockJobApi;
