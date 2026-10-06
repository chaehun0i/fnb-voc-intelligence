import { expect, it, vi } from "vitest";
import { verificationFixture } from "../../test/verificationFixture";
import { createHttpAgentRunApi, decodeDetail } from "./api";

it("멀티 조사 거래·재고 참조도 기존 내부 검증 lineage로 조회한다", () => {
  const run = verificationFixture("PASS");
  const source = run.normalized_evidence![0];
  const result = decodeDetail({ ...run, workflow_version: "multi-investigation-v5",
    normalized_evidence: [...run.normalized_evidence!, { ...source, source_ref: "transaction:t1", source_id: "t1", source_type: "TRANSACTION", step_name: "investigation_fan_in", observation_code: "REFUND_SIGNAL", stance: "NEUTRAL", provenance: ["synthetic_operational"] }],
    verification_evidence: run.verification_evidence!.map((e) => ({ ...e, additional_evidence_refs: ["review:r1", "transaction:t1"] })) });
  expect(result.verification_evidence![0].additional_evidence_refs).toContain("transaction:t1");
});

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
