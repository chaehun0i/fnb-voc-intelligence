import { mockApi } from "../mockApi";
import { decodeIncident } from "../incidents";
import { apiBaseUrl, apiMode, authHeaders } from "../client";
import type { Approval, ReviewAction, ReviewDetail } from "../../contracts/types";

export class ReviewApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string) {
    super(message); this.name = "ReviewApiError";
  }
}

export interface ReviewApi {
  listApprovals(): Promise<Approval[]>;
  getReviewDetail(id: string): Promise<ReviewDetail | undefined>;
  reviewAction(id: string, action: ReviewAction, note: string, key: string, version?: number): Promise<void>;
}

const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const date = (value: unknown) => typeof value === "string" && Number.isFinite(Date.parse(value));
const text = (value: unknown) => typeof value === "string";
function invalid(): never { throw new ReviewApiError("CONTRACT_ERROR", "검토 응답 형식이 올바르지 않습니다. 관리자에게 알려 주세요."); }

export function decodeApproval(value: unknown): Approval {
  if (!record(value) || !["id", "incident_id", "type", "requester"].every((key) => text(value[key])) ||
    !date(value.requested_at) || !["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(String(value.risk_level)) ||
    !["PENDING", "APPROVED", "REJECTED"].includes(String(value.status)) ||
    !Number.isInteger(value.version) || Number(value.version) < 1 ||
    typeof value.evidence_completeness !== "number" || value.evidence_completeness < 0 || value.evidence_completeness > 100 ||
    !record(value.actions)) invalid();
  for (const action of ["approve", "reject", "edit", "request_more_evidence"]) {
    const permission = (value.actions as Record<string, unknown>)[action];
    if (!record(permission) || typeof permission.allowed !== "boolean" || !text(permission.reason)) invalid();
  }
  return value as unknown as Approval;
}

function decodeDetail(value: unknown): ReviewDetail {
  if (!record(value) || !["approval_id", "incident_display_id", "incident_title", "proposed_action", "expected_effect", "verification_criteria"].every((key) => text(value[key])) ||
    !date(value.due_at) || !Array.isArray(value.evidence) || !Array.isArray(value.history)) invalid();
  if (!value.evidence.every((e) => record(e) && ["id", "source", "type", "summary"].every((key) => text(e[key])) &&
    typeof e.confidence === "number" && e.confidence >= 0 && e.confidence <= 1 && ["AVAILABLE", "PENDING", "REJECTED"].includes(String(e.status))) ||
    !value.history.every((e) => record(e) && date(e.occurred_at) && text(e.actor) && text(e.summary))) invalid();
  return value as unknown as ReviewDetail;
}

export function createHttpReviewApi(baseUrl: string, fetcher: typeof fetch = fetch): ReviewApi {
  async function request(path: string, body?: object, key?: string) {
    let response: Response;
    try {
      response = await fetcher(`${baseUrl.replace(/\/+$/, "")}/reviews${path}`, {
        method: body ? "POST" : "GET",
        headers: { Accept: "application/json", ...authHeaders(), ...(body ? { "Content-Type": "application/json", "Idempotency-Key": key! } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
    } catch { throw new ReviewApiError("NETWORK_ERROR", "서버에 연결하지 못했습니다. 연결 상태를 확인한 뒤 같은 내용으로 다시 시도해 주세요."); }
    let payload: unknown;
    try { payload = await response.json(); } catch {
      throw new ReviewApiError(response.ok ? "CONTRACT_ERROR" : "HTTP_ERROR", "서버 응답을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.");
    }
    if (!response.ok) {
      const error = record(payload) && record(payload.error) ? payload.error : undefined;
      const code = error && text(error.code) ? String(error.code) : `HTTP_${response.status}`;
      const messages: Record<string, string> = {
        AUTHENTICATION_REQUIRED: "로그인이 필요합니다. 개발 계정 설정을 확인해 주세요.",
        INVALID_CREDENTIALS: "인증 정보가 유효하지 않습니다. 계정 설정을 확인해 주세요.",
        AUTHORIZATION_DENIED: "현재 계정에는 이 검토를 결정할 권한이 없습니다.",
        IDEMPOTENCY_CONFLICT: "같은 요청 키의 내용이 달라 충돌했습니다. 최신 자료를 다시 확인해 주세요.",
        CONFLICT: "이미 결정되었거나 조치안이 바뀌었습니다. 목록을 다시 불러와 주세요.",
        PROCESSING: "요청 처리 중입니다. 잠시 후 같은 내용으로 다시 시도해 주세요.",
      };
      throw new ReviewApiError(code, messages[code] ?? (error && text(error.message) ? String(error.message) : "검토 요청을 처리하지 못했습니다."),
        record(payload) && text(payload.request_id) ? String(payload.request_id) : undefined);
    }
    return payload;
  }
  return {
    listApprovals: async () => {
      const payload = await request("");
      if (!Array.isArray(payload)) invalid();
      return payload.map(decodeApproval);
    },
    getReviewDetail: async (id) => {
      const payload = await request(`/${encodeURIComponent(id)}`);
      if (!record(payload)) invalid();
      decodeApproval(payload.approval);
      return decodeDetail(payload.detail);
    },
    reviewAction: async (id, action, note, key, version) => {
      if (action !== "approve" && action !== "reject") throw new ReviewApiError("UNSUPPORTED_ACTION", "현재 서버는 승인·반려만 지원합니다.");
      if (!note.trim()) throw new ReviewApiError("VALIDATION_ERROR", "결정 사유를 입력해 주세요.");
      decodeIncident(await request(`/${encodeURIComponent(id)}/${action}`, { reason: note.trim(), expected_version: version }, key));
    },
  };
}

export const mockReviewApi: ReviewApi = {
  listApprovals: () => mockApi.listApprovals(),
  getReviewDetail: (id) => mockApi.getReviewDetail(id),
  reviewAction: async (id, action, note) => { await mockApi.reviewAction(id, action, note); },
};
export const reviewApi = apiMode === "http" ? createHttpReviewApi(apiBaseUrl) : mockReviewApi;
export const reviewAsOf = () => apiMode === "mock" ? mockApi.asOf : new Date().toISOString();
