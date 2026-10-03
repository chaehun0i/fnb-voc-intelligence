import { describe, expect, it, vi } from "vitest";
import { createHttpJobApi, decodeJob, mockJobApi } from ".";

export const jobResponse = { id: "job", tenant_id: "tenant", type: "incident.snapshot", status: "PENDING", priority: "P2", queued_at: "2026-10-03T00:00:00Z", available_at: "2026-10-03T00:00:00Z", attempts: 0, max_attempts: 3, config_version: 1, version: 1, correlation_id: "chain", incident_id: null, parent_job_id: null, error_code: null, error_summary: null, started_at: null, completed_at: null, lease_until: null, actions: { retry: { allowed: false, reason: "실패 작업만 재시도할 수 있습니다." }, cancel: { allowed: true, reason: "취소할 수 있습니다." } } };

describe("Job 계약", () => {
  it("Mock 경로를 보존한다", async () => { expect((await mockJobApi.listJobs()).length).toBeGreaterThan(0); });
  it("HTTP 목록과 상세를 검증한다", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify([jobResponse]))).mockResolvedValueOnce(new Response(JSON.stringify(jobResponse)));
    const api = createHttpJobApi("http://localhost/api/v1", fetcher);
    expect((await api.listJobs())[0].status).toBe("PENDING");
    expect((await api.getJob("job"))?.id).toBe("job");
  });
  it("잘못된 시각과 permission을 거부한다", () => {
    expect(() => decodeJob({ ...jobResponse, queued_at: "invalid" })).toThrow();
    expect(() => decodeJob({ ...jobResponse, actions: {} })).toThrow();
  });
  it("운영 명령에 같은 요청 키를 전달한다", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...jobResponse, status: "CANCELLED" })));
    await createHttpJobApi("http://localhost/api/v1", fetcher).jobAction("job", "cancel", "작업 취소", "same-key", 1);
    expect(fetcher.mock.calls[0][1].headers["Idempotency-Key"]).toBe("same-key");
    expect(JSON.parse(fetcher.mock.calls[0][1].body).reason).toBe("작업 취소");
  });
  it("권한 오류를 안전한 메시지로 변환한다", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "AUTHORIZATION_DENIED", message: "현재 역할에서는 처리할 수 없습니다." }, request_id: "request" }), { status: 403 }));
    await expect(createHttpJobApi("http://localhost", fetcher).listJobs()).rejects.toMatchObject({ code: "AUTHORIZATION_DENIED", requestId: "request" });
  });
});
