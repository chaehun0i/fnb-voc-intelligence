import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AgentRunApi } from "./api";
import { historyFixture } from "../../test/agentRunFixture";
import { HistoryTracePanel } from "./HistoryTrace";

it("실제 조사 근거·공백·사용량·Config와 상세 새로고침을 표시한다", async () => {
  const detail = vi.fn().mockResolvedValue(historyFixture);
  const api: AgentRunApi = { list: vi.fn().mockResolvedValue({ runs: [historyFixture], limit: 20, offset: 0, has_more: false }), detail };
  render(<HistoryTracePanel incidentId="incident-1" api={api} />);
  expect(screen.getByText("실제 History 조사 기록을 불러오는 중입니다")).toBeInTheDocument();
  expect(await screen.findByText("과거 VOC와 유사 사례를 조사했습니다.")).toBeInTheDocument();
  expect(screen.getByText("관련 이력이 부족해 추가 근거가 필요합니다.")).toBeInTheDocument();
  expect(screen.getAllByText("review:r1").length).toBeGreaterThan(0);
  expect(screen.getByText("v1 / history-v1")).toBeInTheDocument();
  expect(screen.getByText("15")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "조사 기록 새로고침" }));
  await screen.findByText("과거 VOC와 유사 사례를 조사했습니다.");
  expect(detail.mock.calls.length).toBeGreaterThanOrEqual(2);
});

it("빈 이력은 미래 Agent 실행처럼 표시하지 않는다", async () => {
  render(<HistoryTracePanel incidentId="i" api={{ list: async () => ({ runs: [], limit: 20, offset: 0, has_more: false }), detail: vi.fn() }} />);
  expect(await screen.findByText("아직 실행된 History 조사가 없습니다")).toBeInTheDocument();
});

it("HTTP 오류·권한 부족을 예시로 대체하지 않는다", async () => {
  const api = { list: vi.fn().mockRejectedValue(new Error("현재 계정은 조회 권한이 없습니다. · 요청 ID: req-1")), detail: vi.fn() };
  render(<HistoryTracePanel incidentId="i" api={api} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("조회 권한이 없습니다");
  expect(screen.getByRole("alert")).toHaveTextContent("req-1");
  expect(api.detail).not.toHaveBeenCalled();
  expect(screen.queryByText("과거 VOC와 유사 사례를 조사했습니다.")).not.toBeInTheDocument();
});
