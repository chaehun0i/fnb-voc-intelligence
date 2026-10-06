import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { fetcher } = vi.hoisted(() => {
  const fetcher = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetcher);
  vi.stubEnv("VITE_API_MODE", "http");
  return { fetcher };
});
import { ReviewQueue } from "./ReviewQueue";
import { mockApi, resetMockState } from "../../shared/mockApi";
import type { Approval } from "../../contracts/types";

beforeEach(() => { resetMockState(); fetcher.mockReset(); });

describe("실제 HTTP 모드의 Review 화면", () => {
  it("HTTP 원본과 권한을 표시하고 연결 실패 재시도를 같은 키로 승인한다", async () => {
    let approval: Approval = { ...(await mockApi.listApprovals())[0], version: 1 };
    const detail = await mockApi.getReviewDetail(approval.id);
    const incident = { ...(await mockApi.getIncident("inc-1"))!, version: 2, priority: "P1" };
    let attempts = 0;
    fetcher.mockImplementation(async (url, init) => {
      if (init?.method === "POST") {
        attempts++;
        if (attempts === 1) throw new TypeError("접속 종료");
        approval = { ...approval, status: "APPROVED", version: 2, actions: Object.fromEntries(
          Object.keys(approval.actions).map((key) => [key, { allowed: false, reason: "이미 승인되었습니다." }]),
        ) as Approval["actions"] };
        return Response.json(incident);
      }
      return Response.json(String(url).endsWith("/reviews") ? [approval] : { approval, detail });
    });
    render(<ReviewQueue />);
    expect(screen.getByText("검토 요청을 불러오는 중입니다")).toBeVisible();
    fireEvent.click(await screen.findByRole("button", { name: /INC-2026-001/ }));
    expect(screen.getByText(/실제 서버의 승인 기록입니다/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("결정 사유 또는 요청 내용"), { target: { value: "증거 확인 완료" } });
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("서버에 연결하지 못했습니다");
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    await screen.findByText("승인됨");
    await waitFor(() => expect(screen.getByRole("button", { name: "승인" })).toBeDisabled());
    const posts = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(2);
    expect(posts[0][1]?.headers).toEqual(posts[1][1]?.headers);
    expect(JSON.parse(posts[0][1]?.body as string)).toEqual({ reason: "증거 확인 완료", expected_version: 1 });
  });

  it("HTTP 권한 오류를 로딩·빈 목록과 구분해 안내한다", async () => {
    fetcher.mockImplementation(async () => Response.json({ error: { code: "AUTHORIZATION_DENIED" } }, { status: 403 }));
    render(<ReviewQueue />);
    expect(await screen.findByText("현재 계정에는 이 검토를 결정할 권한이 없습니다.")).toBeVisible();
    expect(screen.queryByText("등록된 검토 요청이 없습니다")).not.toBeInTheDocument();
  });
});
