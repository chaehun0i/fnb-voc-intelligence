import { expect, it, vi } from "vitest";
import { verificationFixture } from "../../test/verificationFixture";
import { createHttpAgentRunApi, decodeDetail } from "./api";

it.each(["PASS", "FAIL", "INCONCLUSIVE"] as const)("HTTP 계약에서 %s와 v4 lineage를 유지한다", (result) => {
  expect(decodeDetail(verificationFixture(result)).verification?.result).toBe(result);
});
it("외부 실행 모드와 존재하지 않는 검증 근거를 거부한다", () => {
  const run = verificationFixture("PASS");
  expect(() => decodeDetail({ ...run, execution: { ...run.execution, execution_mode: "EXTERNAL" } })).toThrow();
  expect(() => decodeDetail({ ...run, verification: { ...run.verification, evidence_ids: ["fabricated"] } })).toThrow();
  expect(() => decodeDetail({ ...run, execution: { ...run.execution, incident_id: "another" } })).toThrow();
});
it("HTTP 실패를 검증 fixture로 대체하지 않는다", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "FORBIDDEN" }, request_id: "verification-request" }), { status: 403 }));
  await expect(createHttpAgentRunApi("/api/v1", fetcher).detail("i", "r")).rejects.toMatchObject({ code: "FORBIDDEN", requestId: "verification-request" });
  expect(fetcher).toHaveBeenCalledTimes(1);
});
