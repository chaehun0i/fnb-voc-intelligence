import { expect, it } from "vitest";
import { decodeRun } from "./api";
import { evidenceFixture } from "../../test/evidenceFixture";

it("파일 Import 근거의 출처를 보존하고 알 수 없는 출처는 거부한다", () => {
  const imported = { ...evidenceFixture, normalized_evidence: evidenceFixture.normalized_evidence!.map((e) => ({ ...e, provenance: ["file_imported_operational"] })) };
  expect(decodeRun(imported).normalized_evidence?.[0].provenance).toEqual(["file_imported_operational"]);
  expect(() => decodeRun({ ...imported, normalized_evidence: imported.normalized_evidence.map((e) => ({ ...e, provenance: ["untrusted"] })) })).toThrow("응답 형식");
});

it("실제 서버 근거·충분성·RCA 응답을 계산 없이 디코딩한다", () => {
  const result = decodeRun(evidenceFixture);
  expect(result.sufficiency?.status).toBe("SUFFICIENT");
  expect(result.rca_candidates?.[0].supporting_refs).toEqual(["review:r1", "review:r2"]);
});
it.each([
  { supporting_refs: ["review:missing"] }, { confidence: 2 }, { config_version: 99 },
  { contradicting_refs: ["review:r1"] }, { jev_decision_id: "other" }, { code: "INVENTED_CAUSE" },
])("유효하지 않은 RCA lineage/근거 %s를 거부한다", (change) => {
  expect(() => decodeRun({ ...evidenceFixture, rca_candidates: [{ ...evidenceFixture.rca_candidates![0], ...change }] })).toThrow("응답 형식");
});
it("부족한 근거를 성공 RCA로 위장하거나 다른 실행의 근거를 섞지 않는다", () => {
  expect(() => decodeRun({ ...evidenceFixture, sufficiency: { ...evidenceFixture.sufficiency, status: "INSUFFICIENT" } })).toThrow("응답 형식");
  expect(() => decodeRun({ ...evidenceFixture, normalized_evidence: [{ ...evidenceFixture.normalized_evidence![0], agent_run_id: "other" }] })).toThrow("응답 형식");
});
