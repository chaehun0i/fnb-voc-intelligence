import { describe, expect, it, vi } from "vitest";
import { createHttpDashboardApi, decodeDashboard, mockDashboardApi } from ".";

describe("Dashboard 계약", () => {
  it("명시적 KPI와 미구현 연동 상태를 단일 Snapshot으로 반환한다", async () => {
    const snapshot = await mockDashboardApi.getSnapshot();
    expect(snapshot.window).toBe("7d");
    expect(snapshot.timezone).toBe("UTC");
    expect(snapshot.kpis.open_incidents).toBeGreaterThanOrEqual(0);
    expect(snapshot.integration_health.status).toBe("NOT_IMPLEMENTED");
    expect(snapshot.incident_trend).toHaveLength(7);
  });
});

async function responseSnapshot() {
  const fixture = await mockDashboardApi.getSnapshot();
  return { ...fixture, as_of: "2026-10-03T10:00:00Z", incident_trend: Array.from({ length: 7 }, (_, n) => ({ day: new Date(Date.UTC(2026, 8, 27 + n)).toISOString().slice(0, 10), detected: n, resolved: 0 })) };
}

describe("Dashboard HTTP", () => {
  it("한 endpoint의 응답만 사용한다", async () => {
    const body = await responseSnapshot();
    const transport = vi.fn().mockResolvedValue(new Response(JSON.stringify(body)));
    expect(await createHttpDashboardApi("/api/v1/", transport).getSnapshot()).toEqual(body);
    expect(transport).toHaveBeenCalledOnce();
    expect(transport.mock.calls[0][0]).toBe("/api/v1/dashboard?window=7d");
  });
  it("잘못된 날짜/KPI/연동 계약은 거부한다", async () => {
    const body = await responseSnapshot();
    for (const invalid of [{ ...body, as_of: "bad" }, { ...body, kpis: { ...body.kpis, failed_jobs: -1 } }, { ...body, incident_trend: [] }, { ...body, integration_health: { status: "HEALTHY" } }]) {
      expect(() => decodeDashboard(invalid)).toThrow("응답 형식");
    }
  });
  it.each([401, 403, 503])("HTTP %s를 예시로 대체하지 않는다", async (status) => {
    const mock = vi.spyOn(mockDashboardApi, "getSnapshot");
    const transport = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "DENIED", message: "secret" }, request_id: "req-a" }), { status }));
    await expect(createHttpDashboardApi("/api/v1", transport).getSnapshot()).rejects.toMatchObject({ code: "DENIED", requestId: "req-a" });
    expect(mock).not.toHaveBeenCalled();
    mock.mockRestore();
  });
  it("network 오류를 안정적인 코드로 표시한다", async () => {
    await expect(createHttpDashboardApi("/api/v1", vi.fn().mockRejectedValue(new Error("secret"))).getSnapshot()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
