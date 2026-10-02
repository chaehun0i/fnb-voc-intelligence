import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHttpIncidentApi } from "./index";
import { mockApi, resetMockState } from "../mockApi";

beforeEach(() => resetMockState());
describe("Incident HTTP 계약", () => {
  it("목록·상세·workspace를 동일한 계약으로 읽는다", async () => {
    const incident = await mockApi.getIncident("inc-1");
    const workspace = await mockApi.getIncidentWorkspace("inc-1");
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
});
describe("Mock 계약 상태 격리", () => {
  it("조회 결과를 수정해도 원본 fixture는 유지한다", async () => {
    const items = await mockApi.listIncidents(); items[0].title = "변경";
    expect((await mockApi.listIncidents())[0].title).not.toBe("변경");
  });
});
