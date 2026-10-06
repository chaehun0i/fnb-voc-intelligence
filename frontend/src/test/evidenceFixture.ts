import type { HistoryRunDetail } from "../features/ai/api";
import { historyFixture } from "./agentRunFixture";

export const evidenceFixture: HistoryRunDetail = {
  ...historyFixture, workflow_version: "history-evidence-v2", evidence_gaps: [],
  normalized_evidence: ["r1", "r2"].map((id, index) => ({
    source_ref: `review:${id}`, source_id: id, source_type: "VOC_REVIEW", rank: index + 1,
    retrieved_at: "2026-10-06T00:00:00Z", source_at: "2026-10-05T00:00:00Z",
    agent_run_id: historyFixture.agent_run_id, step_name: "history_investigation", provenance: ["lexical", "vector"],
    stance: "SUPPORTING", observation_code: "RELATED_HISTORY_MATCH",
  })),
  sufficiency: { status: "SUFFICIENT", policy_version: "history-support-v1", evaluated_dimensions: ["SOURCE_COVERAGE", "OBSERVATION_SUPPORT", "CONTRADICTION"],
    supporting_refs: ["review:r1", "review:r2"], contradicting_refs: [], evidence_gaps: [], reason_codes: ["SUFFICIENT_HISTORY_SUPPORT"] },
  rca_candidates: [{ candidate_id: "candidate-1", code: "REPEATED_HISTORY_SIGNAL", hypothesis: "반복 불만 이력이 관측되어 공통 원인에 대한 추가 조사가 필요합니다.",
    confidence: .5, supporting_refs: ["review:r1", "review:r2"], contradicting_refs: [], unresolved_gaps: [],
    provenance: "HISTORY_HYPOTHESIS_NOT_CONFIRMED", generated_by: "DETERMINISTIC", config_version: 1,
    jev_decision_id: historyFixture.jev_decision_id, llm_request_id: null }],
};
