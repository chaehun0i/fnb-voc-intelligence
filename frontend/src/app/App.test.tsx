import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "./App";

describe("ServIQ app", () => { it("renders Korean operations navigation", () => { render(<App />); expect(screen.getByText("오늘의 운영 현황")).toBeInTheDocument(); expect(screen.getByText("인시던트")).toBeInTheDocument(); expect(screen.getByText("실행 추적")).toBeInTheDocument(); expect(screen.getByText("운영 설정")).toBeInTheDocument(); }); });

describe("인시던트 화면", () => { it("목록을 유지한 채 상세를 팝업으로 연다", async () => { render(<App />); fireEvent.click(screen.getByRole("button", { name: "인시던트" })); const title = await screen.findByText("강남점 냉장 보관 온도 이탈"); fireEvent.click(title); expect(await screen.findByRole("dialog")).toBeInTheDocument(); expect(screen.getByText("시정·예방 조치(CAPA)")).toBeInTheDocument(); }); });
