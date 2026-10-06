import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { incidentApi } from "../../api/incidents";
import { mockApi, resetMockState } from "../../api/mockApi";
import { ageLabel } from "../../lib/display";
import { IncidentList } from "./IncidentList";

const mode = vi.hoisted(() => ({ value: "mock" }));
vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, get apiMode() { return mode.value; } };
});

beforeEach(() => {
  resetMockState();
  mode.value = "mock";
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-03T10:00:00Z"));
});
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("인시던트 경과 시간 표시", () => {
  it("HTTP 데이터는 화면을 표시하는 현재 시각을 기준으로 경과 시간을 계산한다", async () => {
    mode.value = "http";
    const incident = { ...(await mockApi.getIncident("inc-1"))!, created_at: "2026-10-03T08:30:00Z" };
    vi.spyOn(incidentApi, "listIncidents").mockResolvedValue([incident]);
    render(<IncidentList onSelect={vi.fn()} />);
    expect(await screen.findByText("1시간 30분")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: incident.title })).toBeInTheDocument();
  });

  it("Mock 데이터는 현재 날짜와 관계없이 fixture 기준 시각을 사용한다", async () => {
    const incident = (await mockApi.getIncident("inc-1"))!;
    vi.spyOn(incidentApi, "listIncidents").mockResolvedValue([incident]);
    render(<IncidentList onSelect={vi.fn()} />);
    expect(await screen.findByText(ageLabel(incident.created_at, mockApi.asOf))).toBeInTheDocument();
  });
});
