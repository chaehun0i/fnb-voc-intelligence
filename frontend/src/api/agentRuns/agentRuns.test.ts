import { expect, it, vi } from "vitest";
import { createHttpAgentRunApi, decodeDetail, decodeRun, mockAgentRunApi } from ".";
import { historyFixture } from "../../test/agentRunFixture";

it("동일 서버 계약으로 목록과 상세를 읽는다", async () => {
  const transport = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ runs: [historyFixture], limit: 20, offset: 0, has_more: false }))).mockResolvedValueOnce(new Response(JSON.stringify(historyFixture)));
  const api = createHttpAgentRunApi("/api/v1", transport);
  expect((await api.list("incident-1")).runs[0].agent_run_id).toBe("run-1");
  expect((await api.detail("incident-1", "run-1")).steps).toHaveLength(1);
  expect(transport.mock.calls[1][0]).toBe("/api/v1/incidents/incident-1/agent-runs/run-1");
});

it.each([{ started_at: "invalid" }, { config_version: -1 }, { token_spent: -1 }, { status: "RESOLVED" }, { evidence_candidates: [{ source_ref: "raw PII" }] }])("잘못된 실행 계약 %s를 거부한다", (change) => {
  expect(() => decodeRun({ ...historyFixture, ...change })).toThrow("응답 형식");
});
it("잘못된 단계 시각과 다른 실행의 단계를 거부한다", () => {
  for (const change of [{ completed_at: "invalid" }, { agent_run_id: "other" }]) {
    expect(() => decodeDetail({ ...historyFixture, steps: [{ ...historyFixture.steps[0], ...change }] })).toThrow("응답 형식");
  }
});

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
