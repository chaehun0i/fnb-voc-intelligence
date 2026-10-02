import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "./App";
import { resetMockState } from "../api/mockApi";

beforeEach(() => { resetMockState(); window.history.replaceState(null, "", "/"); });
describe("ServIQ 운영 콘솔", () => {
  it("한글 메뉴와 계산된 대시보드를 표시한다", async () => {
    render(<App />);
    expect(await screen.findByText("오늘의 운영 현황", undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "인시던트" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "실행 추적" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "운영 설정" })).toBeInTheDocument();
    expect(screen.getByText("최근 7일 인시던트 추세")).toBeInTheDocument();
  });
  it("목록을 유지한 채 상세를 팝업으로 연다", async () => {
    render(<App />); fireEvent.click(screen.getByRole("button", { name: "인시던트" }));
    fireEvent.click(await screen.findByRole("button", { name: "강남점 냉장 보관 온도 이탈" }, { timeout: 5000 }));
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
  it("공유한 화면 주소로 상세 팝업을 직접 연다", async () => {
    window.history.replaceState(null, "", "/#/incidents?incident=inc-1");
    render(<App />);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: "증거" })).toBeInTheDocument();
  });
  it("본문 바로가기는 현재 페이지와 주소를 유지하고 본문에 포커스를 둔다", async () => {
    window.history.replaceState(null, "", "/#/queue");
    render(<App />);
    await screen.findByRole("heading", { name: "작업 대기열" }, { timeout: 5000 });
    fireEvent.click(screen.getByRole("link", { name: "본문 바로가기" }));
    expect(window.location.hash).toBe("#/queue");
    expect(screen.getByRole("heading", { name: "작업 대기열" })).toBeInTheDocument();
    expect(screen.getByLabelText("작업 대기열 본문")).toHaveFocus();
  });
});
