import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AgentRunApi } from "./api";
import { historyFixture } from "../../test/agentRunFixture";
import { HistoryTracePanel, InvestigationProgressPanel, RuntimeControls } from "./HistoryTrace";
import type { RuntimeAX } from "./api";

it("부분 실패에서도 확보한 근거와 업무별 범위를 서버 결과로 표시한다", () => {
  render(<InvestigationProgressPanel progress={{ status: "PARTIAL", evidence_count: 3,
    uncertainty: "관측 근거이며 원인 확정은 아닙니다.", updated_at: "2026-10-07T00:00:00Z",
    agents: [{ agent_type: "HISTORY", business_label: "과거 사례 조사", status: "SUCCESS", evidence_count: 2, retryable: false, gap_codes: [], updated_at: "2026-10-07T00:00:00Z" },
      { agent_type: "INVENTORY", business_label: "재고 조사", status: "UNAVAILABLE", evidence_count: 0, retryable: false, gap_codes: ["CAPABILITY_UNAVAILABLE"], updated_at: "2026-10-07T00:00:00Z" }],
    coverage: [{ dimension: "HISTORY", status: "CONFIRMED" }, { dimension: "INVENTORY", status: "MISSING" }] }} />);
  expect(screen.getByText("과거 사례 조사 · 조사 완료")).toBeInTheDocument();
  expect(screen.getByText("재고 조사 · 데이터 사용 불가")).toBeInTheDocument();
  expect(screen.getByText(/근거 3개 확보/)).toBeInTheDocument();
  expect(screen.queryByText(/checkpoint|fan-out|LangGraph/)).not.toBeInTheDocument();
});

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

const runtime: RuntimeAX = { control_status: "RUNNING", control_version: 0, termination_reason: "NO_NEW_EVIDENCE",
  message: "새로운 근거를 찾지 못해 조사를 중단했습니다.", budget_summary: "읽기 조사 2 / 20회",
  remaining_operations: 18, new_evidence: false, human_action: "담당자가 근거를 검토해 주세요.",
  permissions: { pause: true, resume: false, stop: true, takeover: true }, versions: { loop: "bounded-investigation-1" } };

it("서버의 종료 문구와 버튼 권한을 사용하며 제어 실패를 숨기지 않는다", async () => {
  const control = vi.fn().mockRejectedValue(new Error("상태가 바뀌었습니다. 새로고침해 주세요."));
  render(<RuntimeControls runtime={runtime} onControl={control} />);
  expect(screen.getByText(runtime.message)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "자동 조사 재개" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "일시정지" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("상태가 바뀌었습니다");
  const key = control.mock.calls[0][1];
  fireEvent.click(screen.getByRole("button", { name: "일시정지" }));
  await screen.findByRole("alert");
  expect(control.mock.calls[1]).toEqual(["pause", key]);
  expect(screen.queryByText(/LangGraph|checkpoint|provider retry/)).not.toBeInTheDocument();
});

it("수동 인계 후 서버가 금지한 자동 작업 버튼을 활성화하지 않는다", () => {
  render(<RuntimeControls runtime={{ ...runtime, control_status: "MANUAL_TAKEOVER", termination_reason: "MANUAL_TAKEOVER",
    message: "담당자가 직접 처리를 이어가고 있습니다.", permissions: { pause: false, resume: false, stop: false, takeover: false } }} onControl={vi.fn()} />);
  expect(screen.getByText("담당자가 직접 처리를 이어가고 있습니다.")).toBeInTheDocument();
  for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
});
