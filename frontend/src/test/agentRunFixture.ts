import type { HistoryRunDetail } from "../api/agentRuns";

// 외부 모델이나 실제 개인정보가 없는 결정적 HTTP 계약 예시입니다.
export const historyFixture: HistoryRunDetail = {
  agent_run_id: "run-1", incident_id: "incident-1", workflow_id: "workflow-1", job_id: "job-1",
  correlation_id: "correlation-1", config_version: 1, jev_decision_id: "decision-1", workflow_version: "history-v1",
  status: "COMPLETED", started_at: "2026-10-05T09:00:00Z", completed_at: "2026-10-05T09:00:01Z",
  error_code: null, safe_error_summary: null, route: "GENERAL_INVESTIGATION", risk_level: "MEDIUM",
  findings: [{ code: "RELATED_HISTORY_FOUND", evidence_refs: ["review:r1"] }],
  evidence_candidates: [{ source_ref: "review:r1", source_type: "VOC_REVIEW", rank: 1, retrieved_at: "2026-10-05T09:00:00Z" }],
  evidence_gaps: [{ code: "NO_AUTHORIZED_HISTORY" }], token_spent: 15, cost_spent: .001, iteration: 1, tool_call_count: 1,
  steps: [{ agent_run_id: "run-1", sequence: 2, node_name: "history_investigation", attempt: 1, status: "COMPLETED",
    started_at: "2026-10-05T09:00:00Z", completed_at: "2026-10-05T09:00:01Z", latency_ms: 1000,
    token_spent: 15, cost_spent: .001, evidence_refs: ["review:r1"], error_code: null }],
};
