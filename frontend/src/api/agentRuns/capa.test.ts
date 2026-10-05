import { expect, it } from "vitest";
import { decodeDetail } from ".";
import { capaFixture } from "../../test/capaFixture";

it("서버 CAPA와 실제 승인 중단 노드 계약을 해석한다", () => {
  expect(decodeDetail(capaFixture).approval?.phase).toBe("WAITING_APPROVAL");
});
it.each([{ rca_candidate_id: "missing" }, { supporting_evidence_ids: [] }, { verification_criteria: "" },
  { decision_reference: "other" }, { proposed_action_type: "external.write" }])("유효하지 않은 제안 %s를 거부한다", (change) => {
  expect(() => decodeDetail({ ...capaFixture, capa_proposals: [{ ...capaFixture.capa_proposals![0], ...change }] })).toThrow("응답 형식");
});
