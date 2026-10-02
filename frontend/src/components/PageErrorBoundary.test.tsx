import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PageErrorBoundary } from "./PageErrorBoundary";

function FailedPage(): never {
  throw new Error("비공개 내부 오류: private-server-detail");
}

beforeEach(() => { vi.spyOn(console, "error").mockImplementation(() => {}); });
afterEach(() => { vi.restoreAllMocks(); });

describe("페이지 오류 복구 안내", () => {
  it("렌더 오류를 한글 안내로 바꾸고 내부 오류 정보는 화면에 노출하지 않는다", () => {
    render(<PageErrorBoundary><FailedPage /></PageErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("화면을 표시하지 못했습니다");
    expect(screen.getByRole("button", { name: "전체 화면 새로고침" })).toBeInTheDocument();
    expect(screen.queryByText(/private-server-detail/)).not.toBeInTheDocument();
  });

  it("다른 메뉴의 key로 바뀌면 오류 상태를 초기화하고 화면을 표시한다", () => {
    const rendered = render(<PageErrorBoundary key="incidents"><FailedPage /></PageErrorBoundary>);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    rendered.rerender(<PageErrorBoundary key="queue"><h1>작업 대기열</h1></PageErrorBoundary>);
    expect(screen.getByRole("heading", { name: "작업 대기열" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
