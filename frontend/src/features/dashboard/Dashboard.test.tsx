import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { dashboardApi } from "../../api/dashboard";
import { dashboardFixture } from "../../api/fixtures";
import { Dashboard } from "./Dashboard";

afterEach(() => vi.restoreAllMocks());

it("서버 Snapshot 새로고침과 기존 상세·검토·대기열 이동을 유지한다", async () => {
  const first = { ...dashboardFixture, priority_incidents: [{ id: "incident-x", title: "우선 확인 사건", store: "매장", owner: "담당", severity: "CRITICAL" as const }] };
  const get = vi.spyOn(dashboardApi, "getSnapshot").mockResolvedValueOnce(first).mockResolvedValue({ ...first, as_of: "2026-10-03T10:00:00Z", kpis: { ...first.kpis, pending_approvals: 19 } });
  const onIncident = vi.fn(), onReviews = vi.fn(), onQueue = vi.fn();
  render(<Dashboard onIncident={onIncident} onIncidents={vi.fn()} onReviews={onReviews} onQueue={onQueue} />);
  fireEvent.click(await screen.findByRole("button", { name: "우선 확인 사건" }));
  expect(onIncident).toHaveBeenCalledWith("incident-x");
  fireEvent.click(screen.getByRole("button", { name: "검토 대기함" }));
  fireEvent.click(screen.getByRole("button", { name: "대기열 보기" }));
  expect(onReviews).toHaveBeenCalledOnce(); expect(onQueue).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "최신 정보 불러오기" }));
  expect(await screen.findByText("19건")).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(2);
});
