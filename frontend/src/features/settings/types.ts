import type { ActionPermission, ConfigWorkspace, ControlPlaneConfig, Severity } from "../../contracts/types";

// 기존 화면 계약을 유지하면서 실제 서버의 raw/effective와 출처를 구분합니다.
export type RuntimeConfig = Omit<ControlPlaneConfig, "version" | "default_llm_provider" | "fallback_llm_provider"> & {
  default_llm_provider: "gemini" | "ollama";
  fallback_llm_provider: "gemini" | "ollama";
  structured_output_retry: number;
  internal_execution_enabled?: boolean;
  multi_agent_enabled?: boolean;
  loop_enabled?: boolean;
  critical_manual_only: boolean;
  hosted_ai_allowed: boolean;
  llm_enabled_providers?: Array<"gemini" | "ollama">;
  llm_models?: Array<{ provider: "gemini" | "ollama"; model_class: "FAST" | "STANDARD" | "REASONING"; model: string; input_usd_per_million: number; output_usd_per_million: number }>;
  llm_fallback_allowed?: boolean;
  allowed_agent_types: string[];
  blocked_categories: string[];
  provider_concurrency: number;
  provider_timeout_seconds: number;
  required_roles: string[];
  separation_of_duties: boolean;
  critical_approver_count: number;
  priority_policy: "STRICT_PRIORITY";
  backoff_seconds: number;
  allowed_tools: string[];
  verification_window_hours: number;
  approval_policy_by_risk: Record<Severity, boolean>;
};
export type RuntimeRevision = { version: number; parent_version: number | null; rollback_source: number | null; created_at: string; actor: string; reason: string; changes: Array<{ field: string; before: string; after: string }>; snapshot: RuntimeConfig; compared_to_version?: number; rollback_changes?: Array<{ field: string; before: string; after: string }> };
export type RuntimeWorkspace = {
  config: RuntimeConfig & { version: number };
  effective: RuntimeConfig;
  sources: Record<string, string>;
  adjusted_fields: string[];
  current: { created_at: string | null; created_by: string | null; reason: string; parent_version: number | null };
  runtime_status: "NOT_CONNECTED";
  rules: ConfigWorkspace["rules"] & Record<string, { min: number; max: number; integer: boolean }>;
  save_permission: ActionPermission;
  rollback_permission: ActionPermission;
  scope: "TENANT";
};
export type RuntimeHistory = { revisions: RuntimeRevision[]; limit: number; offset: number; has_more: boolean };
export interface SettingsApi {
  current(): Promise<RuntimeWorkspace>;
  history(limit?: number, offset?: number): Promise<RuntimeHistory>;
  save(config: RuntimeConfig, expectedVersion: number, reason: string, key: string): Promise<RuntimeWorkspace>;
  rollback(targetVersion: number, expectedVersion: number, reason: string, key: string): Promise<RuntimeWorkspace>;
}
