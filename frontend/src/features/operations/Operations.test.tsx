import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { mockApi } from "../../shared/mockApi";
import type { AgentRun, Integration, QueueJob } from "../../contracts/types";
import { Integrations } from "./Integrations";
import { Queue } from "./Queue";
import { AgentTrace } from "../ai/AgentTrace";

afterEach(() => vi.restoreAllMocks());

const integration: Integration = {
  id: "pos-test", name: "매출 연결", category: "판매", description: "주문 데이터 연결",
  status: "HEALTHY", last_success_at: "2026-10-02T08:00:00Z", canonical_model: "Transaction",
  mappings: [{ source: "order_id", target: "transaction_id" }],
  sync: { started_at: "2026-10-02T08:00:00Z", ended_at: "2026-10-02T08:01:00Z", read_count: 10, written_count: 9, skipped_count: 1, error_count: 0, cursor_before: "100", cursor_after: "110" },
  actions: { sync: { allowed: true, reason: "동기화를 시작할 수 있습니다." } },
};
const job: QueueJob = {
  id: "job-test", tenant_id: "강남점", type: "재고 증거 수집", status: "DLQ",
  queued_at: "2026-10-02T08:00:00Z", attempts: 3, max_attempts: 3, priority: "P1",
  incident_id: "inc-test", correlation_id: "correlation-test", config_version: 2,
  error_summary: "원본 데이터 연결 시간 초과",
  actions: { retry: { allowed: true, reason: "복구 확인 후 재시도할 수 있습니다." }, cancel: { allowed: false, reason: "실패 보관함 작업은 취소할 수 없습니다." } },
};

describe("연동과 작업 대기열", () => {
  it("연동 상세를 확인하고 계약에서 허용한 동기화 결과를 반영한다", async () => {
    const updated = { ...integration, sync: { ...integration.sync, written_count: 19 } };
    vi.spyOn(mockApi, "listIntegrations").mockResolvedValueOnce([integration]).mockResolvedValue([updated]);
    const sync = vi.spyOn(mockApi, "syncIntegration").mockResolvedValue(updated);
    render(<Integrations />);
    expect(screen.getByText("연동 상태를 불러오는 중입니다")).toBeInTheDocument();
    await screen.findByText("매출 연결");
    fireEvent.click(screen.getByText("매핑과 동기화 상세 보기"));
    expect(screen.getByText("transaction_id")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "동기화 미리보기" }));
    await waitFor(() => expect(sync).toHaveBeenCalledWith("pos-test"));
    expect(await screen.findByText("19건")).toBeInTheDocument();
  });

  it("대기열 오류와 처리 권한을 표시하고 재시도를 API에 위임한다", async () => {
    vi.spyOn(mockApi, "listJobs").mockResolvedValueOnce([job]).mockResolvedValue([{ ...job, status: "QUEUED" }]);
    const retry = vi.spyOn(mockApi, "jobAction").mockResolvedValue({ ...job, status: "QUEUED" });
    render(<Queue />);
    await screen.findByText("재고 증거 수집");
    fireEvent.click(screen.getByRole("button", { name: "재고 증거 수집 상세 보기" }));
    expect(await screen.findByText(job.error_summary!)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
    expect(screen.getByText(job.actions.cancel.reason)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "재시도" }));
    await waitFor(() => expect(retry).toHaveBeenCalledWith("job-test", "retry"));
    expect(await screen.findByText("재고 증거 수집: 재시도 요청이 미리보기에 반영되었습니다.")).toBeInTheDocument();
  });

  it("연동 조회 실패 뒤 새 요청으로 복구한다", async () => {
    const list = vi.spyOn(mockApi, "listIntegrations").mockRejectedValueOnce(new Error("연결 실패")).mockResolvedValue([integration]);
    render(<Integrations />);
    expect(await screen.findByRole("alert")).toHaveTextContent("연동 상태를 불러오지 못했습니다");
    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    expect(await screen.findByText("매출 연결")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });
});

describe("실행 추적", () => {
  it("운영 단계의 판단과 상태 전이, 실패한 도구 호출 근거를 보여준다", async () => {
    const run: AgentRun = {
      id: "run-test", incident_id: "inc-test", status: "FAILED", config_version: 2,
      correlation_id: "correlation-test",
      steps: [{ id: "step-test", name: "Inventory Agent", status: "FAILED", latency_ms: 150,
        retry_count: 2, token_usage: 800, cost_usd: 0.03, decision_summary: "재고 조회 연결이 실패했습니다.",
        state_transition: { from: "INVESTIGATING", to: "BLOCKED" },
        tool_calls: [{ id: "tool-test", name: "inventory.lookup", status: "FAILED", latency_ms: 120, summary: "재고 시스템 연결 시간 초과" }],
      }],
    };
    vi.spyOn(mockApi, "getAgentRun").mockResolvedValue(run);
    render(<AgentTrace />);
    expect(await screen.findByText("재고 조회 연결이 실패했습니다.")).toBeInTheDocument();
    expect(screen.getByText("인시던트 상태: 조사 중 → 보류")).toBeInTheDocument();
    fireEvent.click(screen.getByText("기술 상세와 도구 호출 보기"));
    expect(screen.getByText("재고 시스템 연결 시간 초과")).toBeVisible();
    expect(screen.getByText("inventory.lookup")).toBeVisible();
    expect(screen.getByText("tool-test")).toBeVisible();
  });
});
