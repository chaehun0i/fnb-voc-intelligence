import { describe, expect, it, vi } from "vitest";
import { createHttpReviewApi, mockReviewApi } from "./api";
import { mockApi, resetMockState } from "../../shared/mockApi";

describe("Review HTTP·Mock 계약", () => {
  it("Mock 경로를 유지하며 HTTP 목록·상세를 읽는다", async () => {
    resetMockState();
    const approval = { ...(await mockReviewApi.listApprovals())[0], version: 1 };
    const detail = await mockReviewApi.getReviewDetail(approval.id);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json([approval])).mockResolvedValueOnce(Response.json({ approval, detail }));
    const api = createHttpReviewApi("/api/v1", fetcher);
    expect(await api.listApprovals()).toEqual([approval]);
    expect(await api.getReviewDetail(approval.id)).toEqual(detail);
  });

  it("승인·반려는 사유와 버전·동일 재시도 키를 보낸다", async () => {
    const result = { ...(await mockApi.getIncident("inc-1"))!, version: 2, priority: "P1" };
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => Response.json(result));
    const api = createHttpReviewApi("/api/v1", fetcher);
    await api.reviewAction("a", "approve", "확인 완료", "retry-key", 2);
    await api.reviewAction("a", "approve", "확인 완료", "retry-key", 2);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ headers: { "Idempotency-Key": "retry-key" }, body: JSON.stringify({ reason: "확인 완료", expected_version: 2 }) });
    expect(fetcher.mock.calls[1][1]).toEqual(fetcher.mock.calls[0][1]);
  });

  it.each(["AUTHORIZATION_DENIED", "IDEMPOTENCY_CONFLICT", "CONFLICT", "PROCESSING"])("%s 오류와 요청 ID를 보존한다", async (code) => {
    const api = createHttpReviewApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code }, request_id: "request-1" }, { status: 409 })));
    await expect(api.listApprovals()).rejects.toMatchObject({ code, requestId: "request-1" });
  });

  it("네트워크와 잘못된 날짜를 오류로 구분한다", async () => {
    await expect(createHttpReviewApi("/api/v1", vi.fn<typeof fetch>().mockRejectedValue(new TypeError())).listApprovals()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
    await expect(createHttpReviewApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json([{ requested_at: "날짜 없음" }]))).listApprovals()).rejects.toMatchObject({ code: "CONTRACT_ERROR" });
  });
});
