import { describe, expect, it } from "vitest";
import { mockDashboardApi } from ".";

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
