import type { ControlPlaneConfig, ReviewAction } from "../contracts/types";
import { agentFixture, approvalFixtures, configFixture, dashboardFixture, incidentFixtures, integrationFixtures, jobFixtures, previewTime, reviewFixtures, workspaceFixtures } from "./fixtures";

const clone = <T,>(value: T): T => structuredClone(value);
let approvals = clone(approvalFixtures);
let reviews = clone(reviewFixtures);
let integrations = clone(integrationFixtures);
let jobs = clone(jobFixtures);
let workspace = clone(configFixture);
workspace.revisions = [{ version: 1, created_at: previewTime, actor: "운영 관리자", reason: "초기 운영 설정", changes: [], snapshot: clone(workspace.config) }];

function getApproval(id: string) { const item = approvals.find((value) => value.id === id); if (!item) throw new Error("검토 항목을 찾을 수 없습니다."); return item; }
function denied(reason: string): never { throw new Error(reason); }
function revision(config: ControlPlaneConfig, reason: string) {
  const changes = (Object.keys(config) as Array<keyof ControlPlaneConfig>).filter((key) => key !== "version" && JSON.stringify(workspace.config[key]) !== JSON.stringify(config[key])).map((key) => ({ field: key, before: JSON.stringify(workspace.config[key]), after: JSON.stringify(config[key]) }));
  const next = { ...clone(config), version: workspace.config.version + 1 };
  workspace.config = next;
  workspace.revisions.unshift({ version: next.version, created_at: previewTime, actor: "운영 관리자", reason: reason.trim(), changes, snapshot: clone(next) });
  return clone(workspace);
}
export const mockApi = {
  asOf: previewTime,
  listIncidents: async () => clone(incidentFixtures),
  getIncident: async (id: string) => clone(incidentFixtures.find((item) => item.id === id)),
  getIncidentWorkspace: async (id: string) => clone(workspaceFixtures[id]),
  listApprovals: async () => clone(approvals),
  getReviewDetail: async (id: string) => clone(reviews[id]),
  reviewAction: async (id: string, action: ReviewAction, note: string) => {
    const item = getApproval(id);
    if (!item.actions[action].allowed) denied(item.actions[action].reason);
    if (action !== "approve" && !note.trim()) throw new Error("검토 사유 또는 요청 내용을 입력해 주세요.");
    if (action === "approve" || action === "reject") {
      item.status = action === "approve" ? "APPROVED" : "REJECTED";
      for (const permission of Object.values(item.actions)) { permission.allowed = false; permission.reason = "이미 결정된 검토 항목입니다."; }
    }
    reviews[id].history.push({ occurred_at: previewTime, actor: "검토자", summary: `${{ approve: "승인", edit: "수정 요청", reject: "반려", request_more_evidence: "추가 증거 요청" }[action]}${note.trim() ? ` · ${note.trim()}` : ""}` });
    return clone(item);
  },
  getAgentRun: async () => clone(agentFixture),
  getAgentRunForIncident: async (id: string) => id === agentFixture.incident_id ? clone(agentFixture) : undefined,
  getDashboardSnapshot: async () => clone(dashboardFixture),
  listIntegrations: async () => clone(integrations),
  syncIntegration: async (id: string) => {
    const item = integrations.find((value) => value.id === id);
    if (!item) throw new Error("연동 항목을 찾을 수 없습니다.");
    if (!item.actions.sync.allowed) denied(item.actions.sync.reason);
    item.last_success_at = previewTime; item.sync.ended_at = previewTime;
    return clone(item);
  },
  listJobs: async () => clone(jobs),
  jobAction: async (id: string, action: "retry" | "cancel") => {
    const item = jobs.find((value) => value.id === id);
    if (!item) throw new Error("작업을 찾을 수 없습니다.");
    if (!item.actions[action].allowed) denied(item.actions[action].reason);
    item.status = action === "retry" ? "QUEUED" : "CANCELLED";
    item.actions.retry = { allowed: false, reason: "현재 상태에서는 재시도가 필요하지 않습니다." };
    item.actions.cancel = { allowed: action === "retry", reason: action === "retry" ? "대기 중인 작업을 취소할 수 있습니다." : "이미 취소된 작업입니다." };
    return clone(item);
  },
  getConfig: async () => clone(workspace.config),
  updateConfig: async (patch: Partial<ControlPlaneConfig>) => clone(workspace.config = { ...workspace.config, ...clone(patch) }),
  getConfigWorkspace: async () => clone(workspace),
  saveConfig: async (config: ControlPlaneConfig, reason: string) => {
    if (!workspace.save_permission.allowed) denied(workspace.save_permission.reason);
    if (!reason.trim()) throw new Error("설정 변경 사유를 입력해 주세요.");
    if (config.version !== workspace.config.version) throw new Error("설정이 변경되었습니다. 최신 설정을 다시 불러와 주세요.");
    for (const [key, rule] of Object.entries(workspace.rules)) {
      const value = config[key as keyof ControlPlaneConfig];
      if (typeof value !== "number" || !Number.isFinite(value) || value < rule.min || value > rule.max || (rule.integer && !Number.isInteger(value))) throw new Error(`${key}: ${rule.min}~${rule.max} 범위의 ${rule.integer ? "정수" : "숫자"}를 입력해 주세요.`);
    }
    return revision(config, reason);
  },
  rollbackConfig: async (version: number, reason: string) => {
    if (!workspace.rollback_permission.allowed) denied(workspace.rollback_permission.reason);
    if (!reason.trim()) throw new Error("복원 사유를 입력해 주세요.");
    const previous = workspace.revisions.find((item) => item.version === version);
    if (!previous) throw new Error("설정 버전을 찾을 수 없습니다.");
    return revision(previous.snapshot, reason);
  },
};
export function resetMockState() { approvals = clone(approvalFixtures); reviews = clone(reviewFixtures); integrations = clone(integrationFixtures); jobs = clone(jobFixtures); workspace = clone(configFixture); workspace.revisions = [{ version: 1, created_at: previewTime, actor: "운영 관리자", reason: "초기 운영 설정", changes: [], snapshot: clone(workspace.config) }]; }
