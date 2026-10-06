import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const network = vi.hoisted(() => { vi.stubEnv("VITE_API_MODE", "http"); const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher); return fetcher; });
import { Dashboard } from "./Dashboard";
import { mockApi } from "../../shared/mockApi";

const snapshot = {
  as_of: "2026-10-03T12:00:00Z", window: "7d", timezone: "UTC",
  kpis: { open_incidents: 11, critical_incidents: 3, pending_approvals: 5, failed_jobs: 7, dlq_jobs: 9, queue_depth: 13, running_jobs: 2 },
  incident_trend: Array.from({ length: 7 }, (_, n) => ({ day: new Date(Date.UTC(2026, 8, 27 + n)).toISOString().slice(0, 10), detected: n, resolved: 0 })),
  root_cause_distribution: [{ label: "미분류", count: 4 }],
  capa_status: [{ status: "PROPOSED", count: 6 }, { status: "APPROVED", count: 8 }, { status: "EXECUTED", count: 10 }],
  integration_health: { status: "NOT_IMPLEMENTED", reason: "서버 연동 집계는 준비 중입니다." }, priority_incidents: [],
};
const props = { onIncident: vi.fn(), onIncidents: vi.fn(), onReviews: vi.fn(), onQueue: vi.fn() };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
beforeEach(() => { network.mockReset(); });

describe("실제 Dashboard HTTP 화면", () => {
  it("로딩 후 단일 서버 Snapshot의 KPI·시각·UTC를 표시한다", async () => {
    let complete!: (value: Response) => void;
    network.mockReturnValue(new Promise<Response>((resolve) => { complete = resolve; }));
    render(<Dashboard {...props} />);
    expect(screen.getByText("운영 현황을 불러오는 중입니다")).toBeInTheDocument();
    complete(response(snapshot));
    expect(await screen.findByText("11건")).toBeInTheDocument();
    for (const value of ["3건", "5건", "7건", "9건", "13건"]) expect(screen.getByText(value)).toBeInTheDocument();
    expect(screen.getByText(/정보 기준 시각:/)).toHaveTextContent("UTC");
    expect(screen.getByText(/실제 서버 운영 현황/)).toBeInTheDocument();
    expect(screen.getByText(snapshot.integration_health.reason)).toBeInTheDocument();
    expect(screen.queryByText(/미리보기 데이터/)).not.toBeInTheDocument();
    expect(network).toHaveBeenCalledOnce();
    expect(network.mock.calls[0][0]).toMatch(/\/dashboard\?window=7d$/);
  });
  it("빈 조직은 정상 0 지표와 빈 상태를 보여준다", async () => {
    network.mockResolvedValue(response({ ...snapshot, kpis: Object.fromEntries(Object.keys(snapshot.kpis).map((key) => [key, 0])), incident_trend: snapshot.incident_trend.map((day) => ({ ...day, detected: 0, resolved: 0 })), root_cause_distribution: [], capa_status: snapshot.capa_status.map((item) => ({ ...item, count: 0 })) }));
    render(<Dashboard {...props} />);
    expect(await screen.findByText("현재 조회 범위에 운영 기록이 없습니다.")).toBeInTheDocument();
    expect(screen.getAllByText("0건")).toHaveLength(9);
  });
  it("HTTP 실패를 Mock으로 대체하지 않고 새 조회로 복구한다", async () => {
    const mock = vi.spyOn(mockApi, "getDashboardSnapshot");
    network.mockResolvedValueOnce(response({ error: { code: "DASHBOARD_UNAVAILABLE" }, request_id: "req-dashboard" }, 503)).mockResolvedValue(response(snapshot));
    render(<Dashboard {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("req-dashboard");
    expect(screen.queryByText("11건")).not.toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    expect(await screen.findByText("11건")).toBeInTheDocument();
    mock.mockRestore();
  });
});
