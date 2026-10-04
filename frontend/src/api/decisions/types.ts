// 실행 결과가 아닌 Jev의 Shadow 판단 계약입니다.
export type DecisionRoute = "COLD_CHAIN_INVESTIGATION" | "SUPPLIER_LOT_INVESTIGATION" | "HISTORY_RECURRENCE" | "TRANSACTION_INVESTIGATION" | "GENERAL_INVESTIGATION" | "MANUAL_REVIEW";
export type InvestigationAgent = "TEMPERATURE" | "INVENTORY" | "LOT" | "SUPPLIER" | "HISTORY" | "TRANSACTION";
export interface ShadowDecision {
  decision_id: string;
  incident_id: string;
  source_job_id: string;
  mode: "SHADOW";
  route: DecisionRoute;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  priority: "P1" | "P2" | "P3";
  investigation_agents: InvestigationAgent[];
  requires_llm: boolean;
  requires_human_review: boolean;
  workflow_profile: string;
  budget_profile: string;
  manual_reason: string | null;
  reason_codes: string[];
  config_version: number;
  ruleset_version: string;
  decided_at: string;
  duration_ms: number;
  incident_version: number;
}
export interface DecisionHistory { decisions: ShadowDecision[]; limit: number; offset: number; has_more: boolean }
export interface DecisionApi { history(id: string, limit?: number, offset?: number): Promise<DecisionHistory>; latest(id: string): Promise<ShadowDecision | null> }
