import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { IncidentDetail } from "./IncidentDetail";
import { incidentApi } from "../../api/incidents";
import { resetMockState } from "../../api/mockApi";

beforeEach(() => { vi.restoreAllMocks(); resetMockState(); });
describe("인시던트 상세 회귀", () => {
  it("검증 시각 없는 fixture도 팝업과 7개 탭을 정상 표시한다", async () => {
    render(<IncidentDetail id="inc-1" onBack={() => {}} />);
    expect(screen.getByText("인시던트 상세 정보를 불러오는 중입니다")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "강남점 냉장 보관 온도 이탈" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(7);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "검증" }), { button: 0 });
    expect(await screen.findByText("검증 시각: 기록 없음")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "원인 분석" }), { button: 0 });
    expect(await screen.findByText("반대 근거: 매장 관리자")).toBeInTheDocument();
  });
  it("없음과 API 오류를 구분한다", async () => {
    vi.spyOn(incidentApi, "getIncident").mockResolvedValue(undefined);
    const rendered = render(<IncidentDetail id="none" onBack={() => {}} />);
    expect(await screen.findByText("인시던트를 찾을 수 없습니다")).toBeInTheDocument();
    rendered.unmount();
    vi.spyOn(incidentApi, "getIncident").mockRejectedValue(new Error("연결 오류"));
    render(<IncidentDetail id="failed" onBack={() => {}} />);
    expect(await screen.findByText("상세 정보를 불러오지 못했습니다")).toBeInTheDocument();
    expect(screen.getByText("연결 오류")).toBeInTheDocument();
  });
  it("팝업 닫기 콜백을 제공한다", async () => {
    const close = vi.fn(); render(<IncidentDetail id="inc-1" onBack={close} />);
    await screen.findByRole("heading", { name: "강남점 냉장 보관 온도 이탈" });
    fireEvent.click(screen.getByRole("button", { name: "상세 팝업 닫기" })); expect(close).toHaveBeenCalledOnce();
  });
});
