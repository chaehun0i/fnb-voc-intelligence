import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { historyFixture as historyRunFixture } from "../../test/agentRunFixture";
import { EvidenceTrace } from "./EvidenceTrace";

describe("Evidence Trace", () => {
  it("shows insufficient without invented RCA", () => {
    render(<EvidenceTrace run={{ ...historyRunFixture, normalized_evidence: [], rca_candidates: [], sufficiency: {
      status: "INSUFFICIENT", policy_version: "history-support-v1", evaluated_dimensions: ["SOURCE_COVERAGE"],
      supporting_refs: [], contradicting_refs: [], evidence_gaps: [], reason_codes: ["NO_EVIDENCE"],
    } }} />);
    expect(screen.getByText("근거 부족 · 원인 미확정")).toBeInTheDocument();
    expect(screen.getByText("조회 가능한 근거가 없습니다.")).toBeInTheDocument();
  });
  it("shows conflicting evidence and opens source provenance", () => {
    const ref = "review:r1";
    render(<EvidenceTrace run={{ ...historyRunFixture, normalized_evidence: [{
      source_ref: ref, source_id: "r1", source_type: "VOC_REVIEW", rank: 1,
      retrieved_at: "2026-10-06T00:00:00Z", source_at: null, agent_run_id: historyRunFixture.agent_run_id,
      step_name: "history_investigation", provenance: ["lexical", "vector"], stance: "CONTRADICTING", observation_code: "REFERENCE_ONLY",
    }], sufficiency: { status: "CONFLICTING", policy_version: "history-support-v1", evaluated_dimensions: ["CONTRADICTION"],
      supporting_refs: [], contradicting_refs: [ref], evidence_gaps: [], reason_codes: ["CONFLICTING_EVIDENCE"] } }} />);
    expect(screen.getByText("상충 근거 · 추가 검토 필요")).toBeInTheDocument();
    fireEvent.click(screen.getByText("반대 근거"));
    expect(screen.getByText("lexical + vector")).toBeInTheDocument();
  });
});
