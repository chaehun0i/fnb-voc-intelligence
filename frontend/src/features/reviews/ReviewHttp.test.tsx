import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { reviewApi, ReviewApiError } from "../../api/reviews";
import { mockApi, resetMockState } from "../../api/mockApi";
import { ReviewQueue } from "./ReviewQueue";

beforeEach(() => resetMockState());
afterEach(() => vi.restoreAllMocks());

describe("Review 화면의 제출 안전 경계", () => {
  it("연결 실패 재시도는 같은 키를 사용하고 제출 중 중복 클릭을 막는다", async () => {
    let finish!: () => void;
    const action = vi.spyOn(reviewApi, "reviewAction")
      .mockRejectedValueOnce(new ReviewApiError("NETWORK_ERROR", "연결을 확인해 주세요."))
      .mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; }));
    render(<ReviewQueue />);
    fireEvent.click(await screen.findByRole("button", { name: /INC-2026-001/ }));
    fireEvent.change(screen.getByLabelText("결정 사유 또는 요청 내용"), { target: { value: "확인 완료" } });
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("연결을 확인해 주세요.");
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    expect(screen.getByRole("button", { name: "결과를 기록하는 중…" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "결과를 기록하는 중…" }));
    expect(action).toHaveBeenCalledTimes(2);
    expect(action.mock.calls[0][3]).toBe(action.mock.calls[1][3]);
    finish();
    await screen.findByText("승인 결과를 기록했습니다. 검토 이력에서 확인할 수 있습니다.");
  });

  it("변경한 결정 내용에는 새 키를 사용한다", async () => {
    const action = vi.spyOn(reviewApi, "reviewAction").mockRejectedValue(new ReviewApiError("NETWORK_ERROR", "연결 오류"));
    render(<ReviewQueue />);
    fireEvent.click(await screen.findByRole("button", { name: /INC-2026-001/ }));
    fireEvent.change(screen.getByLabelText("결정 사유 또는 요청 내용"), { target: { value: "첫 사유" } });
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    await screen.findByRole("alert");
    fireEvent.change(screen.getByLabelText("결정 사유 또는 요청 내용"), { target: { value: "변경 사유" } });
    fireEvent.click(screen.getByRole("button", { name: "승인" }));
    await waitFor(() => expect(action).toHaveBeenCalledTimes(2));
    expect(action.mock.calls[0][3]).not.toBe(action.mock.calls[1][3]);
    await screen.findByRole("alert");
  });

  it("서버의 disabled reason과 조회 오류를 그대로 안내한다", async () => {
    const rows = await mockApi.listApprovals();
    vi.spyOn(reviewApi, "listApprovals").mockResolvedValue(rows.map((a) => ({ ...a, actions: { ...a.actions, approve: { allowed: false, reason: "서버에서 검토자 역할이 없다고 판단했습니다." } } })));
    render(<ReviewQueue />);
    fireEvent.click(await screen.findByRole("button", { name: /INC-2026-001/ }));
    expect(screen.getByRole("button", { name: "승인" })).toBeDisabled();
    expect(screen.getByText("서버에서 검토자 역할이 없다고 판단했습니다.")).toBeVisible();
  });
});
