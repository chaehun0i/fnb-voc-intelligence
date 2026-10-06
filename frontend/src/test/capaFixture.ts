import type { HistoryRunDetail } from "../features/ai/api";
import { evidenceFixture } from "./evidenceFixture";

export const capaFixture: HistoryRunDetail = {
  ...evidenceFixture, workflow_version: "history-capa-v3", status: "WAITING_APPROVAL", completed_at: null,
  capa_proposals: [{ capa_proposal_id: "capa-1", incident_id: evidenceFixture.incident_id,
    agent_run_id: evidenceFixture.agent_run_id, rca_candidate_id: evidenceFixture.rca_candidates![0].candidate_id,
    summary: "관련 과거 사례와 현장 절차를 담당자가 재검토합니다.", risk_level: "MEDIUM",
    expected_effect: "반복 불만의 공통 원인과 추가 조사 범위를 확인합니다.",
    verification_criteria: "담당자의 이력·절차 재검토 기록과 추가 근거 목록이 존재해야 합니다.",
    supporting_evidence_ids: ["review:r1", "review:r2"], required_approval: true,
    proposed_action_type: "MANUAL_HISTORY_REVIEW", target_reference: evidenceFixture.incident_id,
    assumptions: ["HISTORY_HYPOTHESIS_NOT_CONFIRMED"], uncertainties: ["PHYSICAL_CAUSE_UNCONFIRMED"],
    config_version: evidenceFixture.config_version, decision_reference: evidenceFixture.jev_decision_id, status: "APPLIED" }],
  approval: { approval_id: "approval-1", action_ids: ["capa-1"], action_digest: "a".repeat(64),
    config_version: evidenceFixture.config_version, incident_version: 5, status: "PENDING", phase: "WAITING_APPROVAL",
    waiting_since: "2026-10-06T09:00:00Z", resumed_at: null, decision_actor: null, decision_reason_code: null },
  steps: [{ ...evidenceFixture.steps[0], sequence: 9, node_name: "approval_interrupt", status: "WAITING_APPROVAL" }],
};
