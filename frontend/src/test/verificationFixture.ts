import type { HistoryRunDetail } from "../features/ai/api";
import type { VerificationResult } from "../features/ai/verification";
import { capaFixture } from "./capaFixture";

export function verificationFixture(result: VerificationResult): HistoryRunDetail {
  const executionId = "11111111-1111-1111-1111-111111111111", evidenceId = "22222222-2222-2222-2222-222222222222";
  return { ...capaFixture, workflow_version: "history-verification-v4", status: "COMPLETED", completed_at: "2026-10-06T10:00:00Z",
    approval: { ...capaFixture.approval!, status: "APPROVED", phase: "READY_TO_EXECUTE" },
    execution: { execution_id: executionId, incident_id: capaFixture.incident_id, agent_run_id: capaFixture.agent_run_id, action_id: "capa-1", approval_id: "approval-1",
      action_digest: "a".repeat(64), execution_mode: "INTERNAL_RECORD_ONLY", status: "SUCCEEDED", started_at: "2026-10-06T09:30:00Z", completed_at: "2026-10-06T09:30:00Z",
      safe_result_summary: "내부 실행 기록만 생성했습니다. 외부 시스템은 변경하지 않았습니다.", config_version: capaFixture.config_version, correlation_id: capaFixture.correlation_id, incident_version: 7 },
    verification_evidence: [{ evidence_id: evidenceId, agent_run_id: capaFixture.agent_run_id, execution_id: executionId, action_id: "capa-1", source_ref: "internal-review:"+evidenceId,
      source_type: "INTERNAL_REVIEW_RECORD", observation_mode: "SIMULATED", observed_at: "2026-10-06T09:30:00Z", review_record_present: result === "PASS" ? true : result === "FAIL" ? false : null, additional_evidence_refs: ["review:r1"] }],
    verification: { verification_id: "33333333-3333-3333-3333-333333333333", incident_id: capaFixture.incident_id, action_id: "capa-1", execution_id: executionId,
      criteria: capaFixture.capa_proposals![0].verification_criteria, evidence_ids: [evidenceId], criterion_results: [{ code: "REVIEW_RECORD_PRESENT", result }, { code: "ADDITIONAL_EVIDENCE_LIST", result: "PASS" }],
      result, confidence: result === "INCONCLUSIVE" ? 0 : 1, summary: "내부 검토 기록의 판정", reason_codes: [result === "PASS" ? "CRITERIA_MET" : result === "FAIL" ? "CRITERIA_NOT_MET" : "EVIDENCE_MISSING"],
      verified_at: "2026-10-06T10:00:00Z", config_version: capaFixture.config_version, observation_mode: "SIMULATED" },
    resulting_incident_status: result === "PASS" ? "RESOLVED" : result === "FAIL" ? "REOPENED" : "VERIFYING",
    steps: [{ ...capaFixture.steps[0], sequence: 14, node_name: "apply_verification", status: "COMPLETED" }],
  };
}
