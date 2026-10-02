import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHttpIncidentApi, createIncident, incidentCommand } from "./index";
import { mockApi, resetMockState } from "../mockApi";

beforeEach(() => resetMockState());
afterEach(() => vi.unstubAllGlobals());

async function httpIncident() {
  return { ...(await mockApi.getIncident("inc-1"))!, version: 1, priority: "P1" };
}

describe("Incident HTTP 계약", () => {
  it("목록·상세·workspace를 동일한 계약으로 읽는다", async () => {
    const incident = await httpIncident();
    const workspace = { ...(await mockApi.getIncidentWorkspace("inc-1"))!, commands: { triage: { allowed: false, reason: "분류가 완료되었습니다." } } };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json([incident])).mockResolvedValueOnce(Response.json(incident)).mockResolvedValueOnce(Response.json(workspace));
    const api = createHttpIncidentApi("http://localhost/api/v1/", fetcher);
    expect(await api.listIncidents()).toEqual([incident]);
    expect(await api.getIncident("inc-1")).toEqual(incident);
    expect(await api.getWorkspace("inc-1")).toEqual(workspace);
    expect(fetcher.mock.calls[2][0]).toBe("http://localhost/api/v1/incidents/inc-1/workspace");
  });
  it("NOT_FOUND를 빈 결과로 구분한다", async () => {
    const api = createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code: "NOT_FOUND", message: "대상이 없습니다." } }, { status: 404 })));
    expect(await api.getIncident("없는-ID")).toBeUndefined();
  });
  it("stable error와 요청 ID를 보존한다", async () => {
    const api = createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code: "CONFLICT", message: "최신 버전을 확인해 주세요." }, request_id: "req-1" }, { status: 409 })));
    await expect(api.listIncidents()).rejects.toMatchObject({ code: "CONFLICT", requestId: "req-1" });
  });
  it("네트워크 및 잘못된 응답을 typed error로 변환한다", async () => {
    await expect(createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockRejectedValue(new TypeError())).listIncidents()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
    await expect(createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ items: [] }))).listIncidents()).rejects.toMatchObject({ code: "CONTRACT_ERROR" });
  });

  it("성공 응답의 JSON 파싱 실패와 요청 ID를 보존한다", async () => {
    const api = createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(new Response("not-json", { headers: { "X-Request-ID": "req-json" } })));
    await expect(api.listIncidents()).rejects.toMatchObject({ code: "CONTRACT_ERROR", requestId: "req-json" });
  });

  it.each([
    ["제목", { title: 42 }],
    ["발생 시각", { created_at: "날짜 없음" }],
    ["데이터 버전", { version: 0 }],
    ["우선순위", { priority: "P0" }],
    ["타임라인", { timeline: [{ status: "UNKNOWN", occurred_at: "2026-10-02T09:00:00Z" }] }],
    ["증거", { evidence: [{ id: "ev-x", source: "센서", type: "기록", summary: "측정 기록", confidence: "높음", status: "AVAILABLE" }] }],
    ["원인 후보", { root_cause_candidates: [{ id: "rca-x", summary: "원인", confidence: 0.8, supporting_evidence_ids: [42], counter_evidence_ids: [] }] }],
    ["조치", { corrective_actions: [{ id: "ca-x", summary: "조치", risk_level: null, expected_effect: "효과", verification_criteria: "기준", status: "PROPOSED" }] }],
    ["검증", { verification: { id: "v-x", result: "PASS", summary: "완료", verified_at: "어제" } }],
  ])("%s 필드의 잘못된 값을 화면에 전달하지 않는다", async (_label, patch) => {
    const api = createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ...(await httpIncident()), ...patch }, { headers: { "X-Request-ID": "req-contract" } })));
    await expect(api.getIncident("inc-1")).rejects.toMatchObject({ code: "CONTRACT_ERROR", requestId: "req-contract" });
  });

  it("선택 필드의 null과 envelope를 읽고 ID를 안전하게 인코딩한다", async () => {
    const incident = await httpIncident();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ data: { ...incident, timeline: [{ status: "DETECTED", occurred_at: incident.created_at, reason: null }], verification: { id: "v-x", result: "INCONCLUSIVE", summary: "검증 대기", verified_at: null } } }));
    const value = await createHttpIncidentApi("/api/v1", fetcher).getIncident("매장/인시던트");
    expect(value?.timeline[0].reason).toBeUndefined();
    expect(value?.verification?.verified_at).toBeUndefined();
    expect(fetcher.mock.calls[0][0]).toBe(`/api/v1/incidents/${encodeURIComponent("매장/인시던트")}`);
  });

  it.each([
    ["작업 목록", { tasks: null }],
    ["작업 기한", { tasks: [{ id: "t-1", title: "확인", owner: "담당자", due_at: "잘못된 날짜", status: "PENDING" }] }],
    ["필수 액션", { actions: {} }],
    ["명령 허용 값", { commands: { triage: { allowed: "false", reason: "보류" } } }],
    ["명령 이유", { commands: { triage: { allowed: false, reason: null } } }],
    ["명령 목록", { commands: [] }],
  ])("workspace의 %s 필드가 잘못되면 거부한다", async (_label, patch) => {
    const workspace = { ...(await mockApi.getIncidentWorkspace("inc-1"))!, commands: {} };
    const api = createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ...workspace, ...patch })));
    await expect(api.getWorkspace("inc-1")).rejects.toMatchObject({ code: "CONTRACT_ERROR" });
  });

  it("JSON이 아닌 실패 응답도 HTTP 코드와 요청 ID로 안내한다", async () => {
    const api = createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(new Response("Gateway error", { status: 503, headers: { "X-Request-ID": "req-gateway" } })));
    await expect(api.listIncidents()).rejects.toMatchObject({ code: "HTTP_ERROR", requestId: "req-gateway" });
  });

  it.each([null, "오류", { error: { code: 409, message: {} } }])("형식이 다른 실패 응답에서 TypeError 대신 안정적인 코드를 반환한다", async (payload) => {
    const api = createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload, { status: 409, headers: { "X-Request-ID": "req-conflict" } })));
    await expect(api.listIncidents()).rejects.toMatchObject({ code: "CONFLICT", requestId: "req-conflict" });
  });

  it("workspace의 NOT_FOUND도 빈 결과로 구분한다", async () => {
    const api = createHttpIncidentApi("/api/v1", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code: "NOT_FOUND", message: "대상이 없습니다." } }, { status: 404 })));
    expect(await api.getWorkspace("missing")).toBeUndefined();
  });
});

describe("Incident HTTP 등록과 명령", () => {
  it("등록과 명령에서 같은 envelope와 Incident 검증을 사용한다", async () => {
    const incident = await httpIncident();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => Response.json({ data: incident }));
    vi.stubGlobal("fetch", fetcher);
    expect(await createIncident({ title: "운영 이슈", severity: "HIGH", store: "강남점", owner: "담당자", priority: "P1" })).toEqual(incident);
    expect(await incidentCommand("inc-1", "triage", { expected_version: 1, severity: "HIGH" })).toEqual(incident);
    expect(fetcher.mock.calls[1][1]).toMatchObject({ method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" } });
    expect(JSON.parse(fetcher.mock.calls[1][1]?.body as string)).toEqual({ expected_version: 1, severity: "HIGH" });
  });

  it("명령의 HTTP 오류에서 header 요청 ID를 보존한다", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code: "DOMAIN_RULE_VIOLATION", message: "승인 조건을 확인해 주세요." } }, { status: 409, headers: { "X-Request-ID": "req-command" } })));
    await expect(incidentCommand("inc-1", "execute", { expected_version: 1 })).rejects.toMatchObject({ code: "DOMAIN_RULE_VIOLATION", requestId: "req-command" });
  });

  it("등록과 명령의 네트워크 실패 및 잘못된 성공 응답을 typed error로 변환한다", async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(Response.json(null));
    vi.stubGlobal("fetch", fetcher);
    await expect(createIncident({ title: "운영 이슈", severity: "HIGH", store: "강남점", owner: "담당자", priority: "P1" })).rejects.toMatchObject({ code: "NETWORK_ERROR" });
    await expect(incidentCommand("inc-1", "triage", { expected_version: 1 })).rejects.toMatchObject({ code: "CONTRACT_ERROR" });
  });
});
describe("Mock 계약 상태 격리", () => {
  it("조회 결과를 수정해도 원본 fixture는 유지한다", async () => {
    const items = await mockApi.listIncidents(); items[0].title = "변경";
    expect((await mockApi.listIncidents())[0].title).not.toBe("변경");
  });
});
