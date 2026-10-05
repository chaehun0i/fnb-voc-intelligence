// Proposal은 외부 실행 명령이 아닙니다. 최종 위험/승인 정책은 서버가 계산합니다.
export type CAPAProposal = {
  capa_proposal_id: string; incident_id: string; agent_run_id: string; rca_candidate_id: string;
  summary: string; risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  expected_effect: string; verification_criteria: string; supporting_evidence_ids: string[];
  required_approval: boolean; proposed_action_type: "MANUAL_HISTORY_REVIEW"; target_reference: string;
  assumptions: string[]; uncertainties: string[]; config_version: number; decision_reference: string;
  status: "PROPOSED" | "APPLIED";
};
