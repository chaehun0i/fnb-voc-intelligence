import type { Incident, IncidentWorkspace, Severity } from "../../contracts/types";
import { mockApi } from "../mockApi";

export class IncidentApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string) { super(message); this.name = "IncidentApiError"; }
}
export type IncidentApi = { listIncidents: () => Promise<Incident[]>; getIncident: (id: string) => Promise<Incident | undefined>; getWorkspace: (id: string) => Promise<IncidentWorkspace | undefined> };
function decodeIncident(value: unknown): Incident {
  if (!value || typeof value !== "object" || !("id" in value) || typeof value.id !== "string" || !("timeline" in value) || !Array.isArray(value.timeline) || !("evidence" in value) || !Array.isArray(value.evidence) || !("root_cause_candidates" in value) || !Array.isArray(value.root_cause_candidates) || !("corrective_actions" in value) || !Array.isArray(value.corrective_actions)) throw new IncidentApiError("CONTRACT_ERROR", "응답 형식을 확인할 수 없습니다. API 버전을 확인해 주세요.");
  return value as Incident;
}
export function createHttpIncidentApi(baseUrl: string, fetcher: typeof fetch = fetch): IncidentApi {
  const base = baseUrl.replace(/\/$/, "");
  async function request(path: string): Promise<unknown> {
    let response: Response;
    try { response = await fetcher(`${base}${path}`, { headers: { Accept: "application/json" } }); } catch { throw new IncidentApiError("NETWORK_ERROR", "API에 연결하지 못했습니다. 연결 상태를 확인해 주세요."); }
    let body: unknown;
    try { body = await response.json(); } catch { throw new IncidentApiError("CONTRACT_ERROR", "API 응답을 읽을 수 없습니다."); }
    if (!response.ok) {
      const payload = body as { error?: { code?: string; message?: string }; detail?: { code?: string; message?: string }; request_id?: string };
      const error = payload.error ?? payload.detail;
      throw new IncidentApiError(error?.code ?? (response.status === 404 ? "NOT_FOUND" : "HTTP_ERROR"), error?.message ?? "요청을 처리하지 못했습니다.", payload.request_id ?? response.headers.get("X-Request-ID") ?? undefined);
    }
    return body && typeof body === "object" && "data" in body ? body.data : body;
  }
  return {
    listIncidents: async () => { const data = await request("/incidents"); if (!Array.isArray(data)) throw new IncidentApiError("CONTRACT_ERROR", "인시던트 목록 형식이 올바르지 않습니다."); return data.map(decodeIncident); },
    getIncident: async (id) => { try { return decodeIncident(await request(`/incidents/${encodeURIComponent(id)}`)); } catch (error) { if (error instanceof IncidentApiError && error.code === "NOT_FOUND") return undefined; throw error; } },
    getWorkspace: async (id) => { try { return await request(`/incidents/${encodeURIComponent(id)}/workspace`) as IncidentWorkspace; } catch (error) { if (error instanceof IncidentApiError && error.code === "NOT_FOUND") return undefined; throw error; } },
  };
}
export const apiMode = import.meta.env.VITE_API_MODE === "http" ? "http" : "mock";
export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
export const incidentApi: IncidentApi = apiMode === "http" ? createHttpIncidentApi(apiBaseUrl) : { listIncidents: mockApi.listIncidents, getIncident: mockApi.getIncident, getWorkspace: mockApi.getIncidentWorkspace };
export async function incidentCommand(id: string, command: string, body: Record<string, unknown>): Promise<Incident> {
  let response: Response;
  try { response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/incidents/${encodeURIComponent(id)}/${command}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); } catch { throw new IncidentApiError("NETWORK_ERROR", "API에 연결하지 못했습니다."); }
  let data;
  try { data = await response.json(); } catch { throw new IncidentApiError("CONTRACT_ERROR", "API 응답을 읽을 수 없습니다."); }
  if (!response.ok) throw new IncidentApiError(data.error?.code ?? "HTTP_ERROR", data.error?.message ?? "요청을 처리하지 못했습니다.", data.request_id);
  return decodeIncident(data);
}
export type IncidentCreateInput = { title: string; severity: Severity; store: string; owner: string; priority: "P1" | "P2" | "P3" };
export async function createIncident(body: IncidentCreateInput): Promise<Incident> {
  let response: Response;
  try { response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/incidents`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); } catch { throw new IncidentApiError("NETWORK_ERROR", "API에 연결하지 못했습니다."); }
  let data;
  try { data = await response.json(); } catch { throw new IncidentApiError("CONTRACT_ERROR", "API 응답을 읽을 수 없습니다."); }
  if (!response.ok) throw new IncidentApiError(data.error?.code ?? "HTTP_ERROR", data.error?.message ?? "등록하지 못했습니다.", data.request_id);
  return decodeIncident(data);
}
