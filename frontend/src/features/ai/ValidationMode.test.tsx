import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ValidationMode } from "./ValidationMode";
import { decodeValidation, validationRequest, type ValidationView } from "./validation";

vi.mock("../data/api", () => ({ intakeStatus: vi.fn(async () => ({ stores: ["매장"], has_data: false })) }));
const view: ValidationView = { session: { session_id: "session", store_id: "매장", status: "ACTIVE", scenario_id: "happy_path", validation_kind: "USER_OBSERVATION", incident_id: null, agent_run_id: null }, task: { business_goal: "이 사건의 원인과 다음 조치를 판단해 주세요." }, journey: { task_success: false, incident_status: null, milestones: [] }, event_limit_reached: false };
beforeEach(() => { sessionStorage.clear(); });
it("비활성 모드는 운영 UI를 유지하고 동의 후 업무 목표만 안내한다", async () => {
  const api = { get: vi.fn(async () => view), start: vi.fn(async () => view.session), signal: vi.fn(async () => {}), finish: vi.fn(async () => {}) };
  render(<ValidationMode route="dashboard" api={api}><p>기존 운영 화면</p></ValidationMode>);
  expect(screen.getByText("기존 운영 화면")).toBeInTheDocument();
  expect(api.get).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "사용자 과업 검증 참여" }));
  expect(await screen.findByRole("button", { name: "과업 시작" })).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "과업 시작" }));
  expect(await screen.findByText(view.task.business_goal)).toBeInTheDocument();
  expect(screen.queryByText(/Checkpoint|MCP|Harness/)).not.toBeInTheDocument();
  expect(api.start).toHaveBeenCalledWith("매장", "happy_path", expect.any(String));
  fireEvent.click(screen.getByRole("button", { name: "다음 행동이 불명확함" }));
  await waitFor(() => expect(api.signal).toHaveBeenCalledWith("session", expect.objectContaining({ friction: "NO_CLEAR_NEXT_ACTION" }), expect.any(String)));
});
it("새로고침은 서버 상태를 조회하고 실패를 완료 상태로 대체하지 않는다", async () => {
  sessionStorage.setItem("serviq-validation-session", "session");
  const api = { get: vi.fn().mockRejectedValue(new Error("denied")), start: vi.fn(), signal: vi.fn(), finish: vi.fn() };
  render(<ValidationMode route="incidents" api={api}><p>운영 화면</p></ValidationMode>);
  expect(await screen.findByRole("alert")).toHaveTextContent("권한과 연결");
  expect(screen.queryByText("과업 완료 확인")).not.toBeInTheDocument();
  expect(screen.getByText("운영 화면")).toBeInTheDocument();
});
it("검증 HTTP 오류와 잘못된 응답을 그대로 실패 처리한다", async () => {
  expect(() => decodeValidation({})).toThrow("형식");
  const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 403 }));
  try { await expect(validationRequest("/sessions/x")).rejects.toThrow("권한"); }
  finally { fetcher.mockRestore(); }
});
