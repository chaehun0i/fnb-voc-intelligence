import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const network = vi.hoisted(() => { vi.stubEnv("VITE_API_MODE", "http"); const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher); return fetcher; });
import { Queue } from "./Queue";

const job = { id: "job-http", tenant_id: "tenant", type: "서버 계약 확인", status: "DLQ", priority: "P2", queued_at: "2026-10-03T00:00:00Z", available_at: "2026-10-03T00:00:00Z", attempts: 3, max_attempts: 3, version: 4, config_version: 1, incident_id: "incident", correlation_id: "chain", parent_job_id: null, error_code: "MAX_ATTEMPTS", error_summary: "최대 시도 횟수 도달", started_at: null, completed_at: null, lease_until: null, actions: { retry: { allowed: true, reason: "재시도할 수 있습니다." }, cancel: { allowed: false, reason: "실패 보관함은 취소할 수 없습니다." } } };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
beforeEach(() => { network.mockReset(); });

describe("실제 Queue HTTP 화면", () => {
  it("로딩 후 빈 작업 상태를 표시한다", async () => {
    let complete!: (value: Response) => void;
    network.mockReturnValue(new Promise<Response>((resolve) => { complete = resolve; }));
    render(<Queue />);
    expect(screen.getByText("작업 목록을 불러오는 중입니다")).toBeInTheDocument();
    complete(response([]));
    expect(await screen.findByText("현재 실행 대기 또는 실패한 작업이 없습니다.")).toBeInTheDocument();
  });
  it("서버 상세와 disabled 사유를 표시하고 같은 요청의 네트워크 재시도 키를 유지한다", async () => {
    const keys: string[] = [];
    let rejectFirst!: (reason: Error) => void;
    network.mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === "POST") {
        keys.push((options.headers as Record<string, string>)["Idempotency-Key"]);
        if (keys.length === 1) return new Promise<Response>((_, reject) => { rejectFirst = reject; });
        return Promise.resolve(response({ ...job, id: "retry-child", status: "PENDING", attempts: 0, version: 1, parent_job_id: job.id }));
      }
      return Promise.resolve(response(url.endsWith("/jobs") ? [job] : job));
    });
    render(<Queue />);
    await screen.findByText(job.type);
    fireEvent.click(screen.getByRole("button", { name: `${job.type} 상세 보기` }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(await screen.findByText(job.actions.cancel.reason)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("작업 처리 사유"), { target: { value: "원인을 확인했습니다." } });
    const retry = screen.getByRole("button", { name: "재시도" });
    fireEvent.click(retry); fireEvent.click(retry);
    expect(keys).toHaveLength(1);
    rejectFirst(new Error("연결 실패"));
    await waitFor(() => expect(screen.getByRole("button", { name: "재시도" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "재시도" }));
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).toBe(keys[1]);
    expect(await screen.findByText("서버 계약 확인: 재시도 요청이 서버에 기록되었습니다.")).toBeInTheDocument();
  });
  it("권한 오류를 사용자 안내와 재조회로 표시한다", async () => {
    network.mockResolvedValueOnce(response({ error: { code: "AUTHORIZATION_DENIED", message: "현재 매장 범위에서는 조회할 수 없습니다." } }, 403)).mockResolvedValue(response([]));
    render(<Queue />);
    expect(await screen.findByRole("alert")).toHaveTextContent("현재 매장 범위에서는 조회할 수 없습니다.");
    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    expect(await screen.findByText("현재 실행 대기 또는 실패한 작업이 없습니다.")).toBeInTheDocument();
  });
});
