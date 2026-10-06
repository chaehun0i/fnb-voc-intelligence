import type { Incident, IncidentWorkspace, Severity } from "../../contracts/types";
import { mockApi } from "../mockApi";
import { apiMode, apiBaseUrl, authHeaders, commandKey } from "../client";

export class IncidentApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string) {
    super(message);
    this.name = "IncidentApiError";
  }
}

export type IncidentApi = {
  listIncidents: () => Promise<Incident[]>;
  getIncident: (id: string) => Promise<Incident | undefined>;
  getWorkspace: (id: string) => Promise<IncidentWorkspace | undefined>;
};
export type IncidentCreateInput = {
  title: string;
  severity: Severity;
  store: string;
  owner: string;
  priority: "P1" | "P2" | "P3";
};

const statuses = ["DETECTED", "TRIAGED", "INVESTIGATING", "RCA_READY", "ACTION_PROPOSED", "PENDING_APPROVAL", "EXECUTING", "VERIFYING", "RESOLVED", "CLOSED", "ESCALATED", "BLOCKED", "FAILED", "REOPENED"];
const severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const priorities = ["P1", "P2", "P3"];
const isRecord = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === "string";
const optionalText = (value: unknown) => value === undefined || value === null || isText(value);
const isChoice = (value: unknown, choices: string[]) => isText(value) && choices.includes(value);
const isNumber = (value: unknown) => typeof value === "number" && Number.isFinite(value);
const isDate = (value: unknown) => isText(value) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const optionalDate = (value: unknown) => value === undefined || value === null || isDate(value);
const arrayOf = (value: unknown, validate: (item: unknown) => boolean) => Array.isArray(value) && value.every(validate);
const textFields = (value: Record<string, unknown>, fields: string[]) => fields.every((field) => isText(value[field]));

function contractError(requestId?: string): never {
  throw new IncidentApiError("CONTRACT_ERROR", "응답 형식이 현재 화면의 계약과 다릅니다. API 버전을 확인해 주세요.", requestId);
}

function isEvidence(value: unknown) {
  return isRecord(value) && textFields(value, ["id", "source", "type", "summary"]) &&
    isNumber(value.confidence) && isChoice(value.status, ["AVAILABLE", "PENDING", "REJECTED"]);
}

function isRootCause(value: unknown) {
  return isRecord(value) && textFields(value, ["id", "summary"]) && isNumber(value.confidence) &&
    arrayOf(value.supporting_evidence_ids, isText) && arrayOf(value.counter_evidence_ids, isText);
}

function isCorrectiveAction(value: unknown) {
  return isRecord(value) && textFields(value, ["id", "summary", "expected_effect", "verification_criteria"]) &&
    isChoice(value.risk_level, severities) && isChoice(value.status, ["PROPOSED", "APPROVED", "EXECUTED"]);
}

function isVerification(value: unknown) {
  return value === undefined || value === null || (isRecord(value) && textFields(value, ["id", "summary"]) &&
    isChoice(value.result, ["PASS", "FAIL", "INCONCLUSIVE"]) && optionalDate(value.verified_at) &&
    optionalText(value.execution_id) && optionalText(value.criteria) &&
    (value.evidence_refs === undefined || arrayOf(value.evidence_refs, isText)) &&
    (value.observation_mode === undefined || value.observation_mode === null || value.observation_mode === "SIMULATED"));
}

export function decodeIncident(value: unknown, requestId?: string): Incident {
  if (!isRecord(value) || !textFields(value, ["id", "display_id", "title", "store", "owner"]) ||
    !isChoice(value.status, statuses) || !isChoice(value.severity, severities) ||
    !isDate(value.created_at) || !isDate(value.sla_due_at) ||
    !Number.isInteger(value.version) || Number(value.version) < 1 || !isChoice(value.priority, priorities) ||
    !arrayOf(value.timeline, (event) => isRecord(event) && isChoice(event.status, statuses) && isDate(event.occurred_at) && optionalText(event.reason)) ||
    !arrayOf(value.evidence, isEvidence) || !arrayOf(value.root_cause_candidates, isRootCause) ||
    !arrayOf(value.corrective_actions, isCorrectiveAction) || !isVerification(value.verification)) {
    contractError(requestId);
  }
  // API가 선택 필드에 반환한 null은 기존 화면의 선택 필드 표현으로 맞춥니다.
  const incident = value as unknown as Incident;
  return {
    ...incident,
    timeline: incident.timeline.map((event) => ({ ...event, reason: event.reason ?? undefined })),
    verification: incident.verification ? { ...incident.verification, verified_at: incident.verification.verified_at ?? undefined } : incident.verification,
  };
}

function isPermission(value: unknown) {
  return isRecord(value) && typeof value.allowed === "boolean" && isText(value.reason);
}

function permissionMap(value: unknown) {
  return isRecord(value) && Object.values(value).every(isPermission);
}

function decodeWorkspace(value: unknown, requestId?: string): IncidentWorkspace {
  if (!isRecord(value) || !isChoice(value.priority, priorities) ||
    !arrayOf(value.tasks, (task) => isRecord(task) && textFields(task, ["id", "title", "owner"]) && isDate(task.due_at) && isChoice(task.status, ["PENDING", "RUNNING", "COMPLETED"])) ||
    !permissionMap(value.actions) || !isRecord(value.actions) ||
    !["investigate", "propose_action", "execute"].every((action) => isPermission(value.actions && (value.actions as Record<string, unknown>)[action])) ||
    !permissionMap(value.commands)) {
    contractError(requestId);
  }
  return value as unknown as IncidentWorkspace;
}

function statusErrorCode(status: number) {
  return status === 404 ? "NOT_FOUND" : status === 409 ? "CONFLICT" : status === 422 ? "VALIDATION_ERROR" : "HTTP_ERROR";
}

function readableString(value: unknown) {
  return isText(value) && value.trim() ? value : undefined;
}

async function requestIncidentJson(baseUrl: string, path: string, fetcher: typeof fetch, input?: object) {
  let response: Response;
  try {
    response = await fetcher(`${baseUrl.replace(/\/+$/, "")}${path}`, {
      method: input === undefined ? "GET" : "POST",
      headers: input === undefined ? { Accept: "application/json", ...authHeaders() } : { Accept: "application/json", ...authHeaders(), "Content-Type": "application/json", "Idempotency-Key": commandKey() },
      ...(input === undefined ? {} : { body: JSON.stringify(input) }),
    });
  } catch {
    throw new IncidentApiError("NETWORK_ERROR", "API에 연결하지 못했습니다. 연결 상태를 확인해 주세요.");
  }

  const headerRequestId = readableString(response.headers.get("X-Request-ID"));
  let payload: unknown;
  try { payload = await response.json(); } catch {
    if (response.ok) throw new IncidentApiError("CONTRACT_ERROR", "API 응답을 읽을 수 없습니다.", headerRequestId);
    throw new IncidentApiError(statusErrorCode(response.status), "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.", headerRequestId);
  }
  const requestId = (isRecord(payload) && readableString(payload.request_id)) || headerRequestId;
  if (!response.ok) {
    const error = isRecord(payload) && (isRecord(payload.error) ? payload.error : isRecord(payload.detail) ? payload.detail : undefined);
    throw new IncidentApiError(
      (error && readableString(error.code)) || statusErrorCode(response.status),
      (error && readableString(error.message)) || "요청을 처리하지 못했습니다. 입력값과 현재 정보를 확인해 주세요.",
      requestId,
    );
  }
  return { data: isRecord(payload) && "data" in payload ? payload.data : payload, requestId };
}

export function createHttpIncidentApi(baseUrl: string, fetcher: typeof fetch = fetch): IncidentApi {
  return {
    listIncidents: async () => {
      const { data, requestId } = await requestIncidentJson(baseUrl, "/incidents", fetcher);
      if (!Array.isArray(data)) contractError(requestId);
      return data.map((item: unknown) => decodeIncident(item, requestId));
    },
    getIncident: async (id) => {
      try {
        const { data, requestId } = await requestIncidentJson(baseUrl, `/incidents/${encodeURIComponent(id)}`, fetcher);
        return decodeIncident(data, requestId);
      } catch (error) {
        if (error instanceof IncidentApiError && error.code === "NOT_FOUND") return undefined;
        throw error;
      }
    },
    getWorkspace: async (id) => {
      try {
        const { data, requestId } = await requestIncidentJson(baseUrl, `/incidents/${encodeURIComponent(id)}/workspace`, fetcher);
        return decodeWorkspace(data, requestId);
      } catch (error) {
        if (error instanceof IncidentApiError && error.code === "NOT_FOUND") return undefined;
        throw error;
      }
    },
  };
}

export const incidentApi: IncidentApi = apiMode === "http" ? createHttpIncidentApi(apiBaseUrl) : {
  listIncidents: mockApi.listIncidents,
  getIncident: mockApi.getIncident,
  getWorkspace: mockApi.getIncidentWorkspace,
};

export async function incidentCommand(id: string, command: string, body: Record<string, unknown>): Promise<Incident> {
  const { data, requestId } = await requestIncidentJson(apiBaseUrl, `/incidents/${encodeURIComponent(id)}/${encodeURIComponent(command)}`, fetch, body);
  return decodeIncident(data, requestId);
}

export async function createIncident(body: IncidentCreateInput): Promise<Incident> {
  const { data, requestId } = await requestIncidentJson(apiBaseUrl, "/incidents", fetch, body);
  return decodeIncident(data, requestId);
}
