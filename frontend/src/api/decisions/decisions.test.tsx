import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShadowDecisionPanel } from "../../features/incidents/ShadowDecisionPanel";
import { createHttpDecisionApi, decisionApi, decodeDecision, mockDecisionApi } from "./index";
import type { ShadowDecision } from "./types";

const decision: ShadowDecision = { decision_id: "d", incident_id: "i", source_job_id: "j", mode: "SHADOW", route: "MANUAL_REVIEW", risk_level: "CRITICAL", priority: "P1", investigation_agents: [], requires_llm: false, requires_human_review: true, workflow_profile: "manual-review-v1", budget_profile: "high", manual_reason: "CRITICAL_MANUAL_GATE", reason_codes: ["CRITICAL_MANUAL_GATE"], config_version: 3, ruleset_version: "1", decided_at: "2026-10-04T09:00:00Z", duration_ms: 2, incident_version: 1, error_code: null };
const history = { decisions: [decision], limit: 5, offset: 0, has_more: false };
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Shadow 판단 HTTP 계약", () => {
  it("history/latest를 읽기 전용으로 조회하고 식별자를 인코딩한다", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify(history))).mockResolvedValueOnce(new Response(JSON.stringify(decision)));
    const api = createHttpDecisionApi("http://test/api/v1/", fetcher);
    expect(await api.history("a/b", 5)).toEqual(history);
    expect(await api.latest("i")).toEqual(decision);
    expect(fetcher.mock.calls[0][0]).toBe("http://test/api/v1/incidents/a%2Fb/decisions?limit=5&offset=0");
    expect(fetcher.mock.calls[0][1]).not.toHaveProperty("body");
  });
  it.each([401, 403, 404, 503])("%s 오류에서 request ID를 보존하고 Mock으로 대체하지 않는다", async (status) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ error: { code: "SAFE_ERROR", message: "secret-internal" }, request_id: "request-1" }), { status }));
    const api = createHttpDecisionApi("http://test", fetcher);
    await expect(api.history("i")).rejects.toMatchObject({ code: "SAFE_ERROR", requestId: "request-1" });
    await expect(api.latest("i")).rejects.not.toHaveProperty("message", "secret-internal");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("네트워크 실패·잘못된 날짜·실행 모드를 구분해 거부한다", async () => {
    expect(() => decodeDecision({ ...decision, decided_at: "bad-date" })).toThrow("응답 형식");
    expect(() => decodeDecision({ ...decision, mode: "EXECUTE" })).toThrow("응답 형식");
    expect(() => decodeDecision({ ...decision, requires_llm: "false" })).toThrow("응답 형식");
    const api = createHttpDecisionApi("http://test", vi.fn<typeof fetch>().mockRejectedValue(new Error("offline")));
    await expect(api.latest("i")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
  it("기록 없는 실제 응답과 명시적 예시 모드가 임의 판단을 생성하지 않는다", async () => {
    const api = createHttpDecisionApi("http://test", vi.fn<typeof fetch>().mockResolvedValue(new Response("null")));
    expect(await api.latest("i")).toBeNull();
    expect(await mockDecisionApi.latest("i")).toBeNull();
    expect((await mockDecisionApi.history("i")).decisions).toEqual([]);
  });
});
describe("Shadow 운영 화면", () => {
  it("loading 이후 Shadow·근거·버전을 표시하고 refresh한다", async () => {
    let finish!: (value: typeof history) => void;
    const fetcher = vi.spyOn(decisionApi, "history").mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; })).mockResolvedValue(history);
    render(<ShadowDecisionPanel incidentId="i" />);
    expect(screen.getByText("판단 기록을 불러오는 중입니다")).toBeInTheDocument();
    finish(history);
    expect(await screen.findByText(/설정 버전 3/)).toBeInTheDocument();
    expect(screen.getByText(/현재 Jev 판단은 실행 경로를 변경하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText(/긴급 위험은 사람 검토로 제한/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다음 기록" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "판단 기록 새로고침" }));
    await screen.findByText(/설정 버전 3/);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("empty와 permission error를 구분하고 재조회할 수 있다", async () => {
    vi.spyOn(decisionApi, "history").mockResolvedValueOnce({ ...history, decisions: [] }).mockRejectedValueOnce(new Error("조회 권한이 없습니다 · 요청 ID: r1"));
    render(<ShadowDecisionPanel incidentId="i" />);
    expect(await screen.findByText("아직 Shadow 판단 기록이 없습니다")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "판단 기록 새로고침" }));
    expect(await screen.findByText(/조회 권한이 없습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/설정 버전 3/)).not.toBeInTheDocument();
  });
  it("판단 실패를 정상 Agent 실행으로 표시하지 않는다", async () => {
    vi.spyOn(decisionApi, "history").mockResolvedValue({ ...history, decisions: [{ ...decision, error_code: "DECISION_INTERNAL_ERROR" }] });
    render(<ShadowDecisionPanel incidentId="i" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("판단을 완료하지 못해");
    expect(screen.getByText(/조사 후보\(미실행\): 없음/)).toBeInTheDocument();
  });
});
