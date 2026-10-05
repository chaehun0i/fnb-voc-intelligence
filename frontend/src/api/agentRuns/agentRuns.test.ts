import { expect, it, vi } from "vitest";
import { createHttpAgentRunApi, mockAgentRunApi } from ".";

it("실제 실행 없는 Mock 경로를 명시한다", async () => {
  expect((await mockAgentRunApi.list("i")).runs).toEqual([]);
});
it.each([401, 403, 404, 503])("HTTP %s 실패를 Mock으로 대체하지 않는다", async (status) => {
  const mock = vi.spyOn(mockAgentRunApi, "list");
  const transport = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "DENIED", message: "secret" }, request_id: "req-1" }), { status }));
  await expect(createHttpAgentRunApi("/api/v1", transport).list("i")).rejects.toMatchObject({ code: "DENIED", requestId: "req-1" });
  expect(mock).not.toHaveBeenCalled();
  mock.mockRestore();
});
it("잘못된 계약과 network 원문을 숨기고 안정적인 오류를 반환한다", async () => {
  await expect(createHttpAgentRunApi("/api/v1", vi.fn().mockResolvedValue(new Response("{}"))).list("i")).rejects.toMatchObject({ code: "CONTRACT_ERROR" });
  await expect(createHttpAgentRunApi("/api/v1", vi.fn().mockRejectedValue(new Error("secret"))).list("i")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
});
