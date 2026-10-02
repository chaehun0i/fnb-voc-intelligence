import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "./App";
import { resetMockState } from "../api/mockApi";

beforeEach(() => resetMockState());
describe("ServIQ 운영 콘솔", () => {
  it("한글 메뉴와 계산된 대시보드를 표시한다", async () => {
    render(<App />);
    expect(await screen.findByText("오늘의 운영 현황")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "인시던트" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "실행 추적" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "운영 설정" })).toBeInTheDocument();
    expect(screen.getByText("최근 7일 인시던트 추세")).toBeInTheDocument();
  });
  it("목록을 유지한 채 상세를 팝업으로 연다", async () => {
    render(<App />); fireEvent.click(screen.getByRole("button", { name: "인시던트" }));
    fireEvent.click(await screen.findByRole("button", { name: "강남점 냉장 보관 온도 이탈" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    const tab = await screen.findByRole("tab", { name: "시정·예방 조치" }); fireEvent.mouseDown(tab, { button: 0 });
    expect(await screen.findByText("시정·예방 조치(CAPA)")).toBeInTheDocument();
  });
  it("각 운영 페이지에 접근할 수 있다", async () => {
    render(<App />);
    for (const label of ["인시던트", "검토 대기함", "실행 추적", "연동 관리", "작업 대기열", "운영 설정"]) {
      fireEvent.click(screen.getByRole("button", { name: label }));
      expect(await screen.findByRole("heading", { name: label })).toBeInTheDocument();
    }
  });
});
