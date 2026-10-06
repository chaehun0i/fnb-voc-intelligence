import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { mockApi, resetMockState } from "../../shared/mockApi";
import { ReviewQueue } from "./ReviewQueue";
import { ControlPlaneSettings } from "../settings/ControlPlaneSettings";

beforeEach(() => resetMockState());
afterEach(() => vi.restoreAllMocks());

describe("검토 대기함", () => {
  it("승인 권한이 없는 항목의 근거와 차단 이유를 표시한다", async () => {
    render(<ReviewQueue />);
    fireEvent.click(await screen.findByRole("button", { name: /INC-2026-004/ }));
    expect(screen.getByRole("button", { name: "승인" })).toBeDisabled();
    expect(screen.getByText("공급사 로트 증빙이 없어 현재는 승인할 수 없습니다.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "판단에 사용한 증거" })).toBeInTheDocument();
    expect(screen.getByText(/검토 기한/)).toBeInTheDocument();
  });

  it("추가 증거 요청 사유를 검증하고 성공한 요청을 이력에 남긴다", async () => {
    render(<ReviewQueue />);
    fireEvent.click(await screen.findByRole("button", { name: /INC-2026-001/ }));
    fireEvent.click(screen.getByRole("button", { name: "추가 증거 요청" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("검토 사유 또는 요청 내용을 입력해 주세요.");
    fireEvent.change(screen.getByLabelText("결정 사유 또는 요청 내용"), { target: { value: "냉각기 정비 기록이 필요합니다." } });
    fireEvent.click(screen.getByRole("button", { name: "추가 증거 요청" }));
    expect(await screen.findByText("추가 증거 요청 결과를 기록했습니다. 검토 이력에서 확인할 수 있습니다.")).toBeInTheDocument();
    expect(await screen.findByText("추가 증거 요청 · 냉각기 정비 기록이 필요합니다.")).toBeInTheDocument();
  });

  it("승인 결과와 새 권한을 목록과 결정 버튼에 반영한다", async () => {
    render(<ReviewQueue />);
    fireEvent.click(await screen.findByRole("button", { name: /INC-2026-001/ }));
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    expect(await screen.findByText("승인됨")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "승인" })).toBeDisabled());
    expect(screen.getAllByText("이미 결정된 검토 항목입니다.")).toHaveLength(4);
  });

  it("정상 빈 목록을 로딩과 구분한다", async () => {
    vi.spyOn(mockApi, "listApprovals").mockResolvedValue([]);
    render(<ReviewQueue />);
    expect(await screen.findByText("등록된 검토 요청이 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("검토 요청을 불러오는 중입니다")).not.toBeInTheDocument();
  });
});

describe("운영 설정", () => {
  it("숫자와 위험별 승인 정책을 변경 이유와 함께 저장하고 버전 차이를 표시한다", async () => {
    render(<ControlPlaneSettings />);
    const iterations = await screen.findByLabelText("최대 에이전트 반복 횟수");
    expect(iterations).toHaveAttribute("min", "1");
    expect(iterations).toHaveAttribute("max", "20");
    expect(iterations).toHaveAttribute("step", "1");
    fireEvent.change(iterations, { target: { value: "10" } });
    fireEvent.click(screen.getByLabelText("낮음 위험도 승인 필요"));
    fireEvent.change(screen.getByLabelText("변경 이유"), { target: { value: "매장 품질 검토 강화" } });
    fireEvent.click(screen.getByRole("button", { name: "변경 내용 저장" }));
    expect(await screen.findByText("설정을 저장했습니다. 현재 버전은 2입니다.")).toBeInTheDocument();
    expect(screen.getByLabelText("낮음 위험도 승인 필요")).toBeChecked();
    expect(screen.getByText("위험도별 사람 승인 정책")).toBeInTheDocument();
    const saved = await mockApi.getConfigWorkspace();
    expect(saved.config.max_agent_iterations).toBe(10);
    expect(saved.config.approval_policy_by_risk.LOW).toBe(true);
  });

  it("저장하지 않은 숫자와 승인 정책을 함께 취소한다", async () => {
    render(<ControlPlaneSettings />);
    const iterations = await screen.findByLabelText("최대 에이전트 반복 횟수");
    fireEvent.change(iterations, { target: { value: "12" } });
    fireEvent.click(screen.getByLabelText("낮음 위험도 승인 필요"));
    fireEvent.click(screen.getByRole("button", { name: "변경 취소" }));
    expect(iterations).toHaveValue(8);
    expect(screen.getByLabelText("낮음 위험도 승인 필요")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "변경 내용 저장" })).toBeDisabled();
  });

  it("이전 설정을 사유와 함께 복원하고 새 버전으로 기록한다", async () => {
    render(<ControlPlaneSettings />);
    fireEvent.change(await screen.findByLabelText("최대 에이전트 반복 횟수"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("변경 이유"), { target: { value: "반복 한도 조정" } });
    fireEvent.click(screen.getByRole("button", { name: "변경 내용 저장" }));
    await screen.findByText("설정을 저장했습니다. 현재 버전은 2입니다.");
    fireEvent.change(screen.getByLabelText("이전 설정을 복원하는 이유"), { target: { value: "기존 운영 한도 복원" } });
    fireEvent.click(screen.getByText(/^버전 1 ·/));
    fireEvent.click(await screen.findByRole("button", { name: "버전 1로 복원" }));
    expect(await screen.findByText("버전 1의 설정을 복원하고 새 버전 3으로 기록했습니다.")).toBeInTheDocument();
    expect(screen.getByLabelText("최대 에이전트 반복 횟수")).toHaveValue(8);
    expect((await mockApi.getConfigWorkspace()).config.version).toBe(3);
  });
});
