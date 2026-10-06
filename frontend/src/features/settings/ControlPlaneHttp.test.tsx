import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createHttpSettingsApi, mockSettingsApi, SettingsApiError, settingsApi } from "./api";
import { mockApi, resetMockState } from "../../shared/mockApi";
import type { RuntimeHistory, RuntimeWorkspace } from "./types";
import { ControlPlaneSettings } from "./ControlPlaneSettings";

vi.mock("../../shared/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../shared/api")>(),
  apiMode: "http", apiBaseUrl: "http://test/api/v1",
}));
let workspace: RuntimeWorkspace;
let history: RuntimeHistory;
beforeEach(async () => {
  resetMockState();
  workspace = await mockSettingsApi.current(); history = await mockSettingsApi.history();
  vi.spyOn(settingsApi, "current").mockResolvedValue(workspace);
  vi.spyOn(settingsApi, "history").mockResolvedValue(history);
});
afterEach(() => vi.restoreAllMocks());

describe("실제 Control Plane 화면", () => {
  it("서버 current/history/effective를 표시하고 Runtime 미연결과 Mock 구분을 유지한다", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => new Response(JSON.stringify(String(url).includes("history") ? history : workspace)));
    const http = createHttpSettingsApi("http://test/api/v1", fetcher);
    vi.mocked(settingsApi.current).mockImplementation(http.current); vi.mocked(settingsApi.history).mockImplementation(http.history);
    render(<ControlPlaneSettings />);
    expect(screen.getByText("운영 설정을 불러오는 중입니다")).toBeInTheDocument();
    await screen.findByLabelText("최대 에이전트 반복 횟수");
    expect(screen.getByText("향후 Runtime 적용 설정 · 현재 Runtime 미연결")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "서버 해석값과 안전 상한" })).toBeInTheDocument();
    expect(screen.queryByText(/미리보기 데이터/)).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("저장된 버전이 없는 조직도 기본값과 빈 이력을 분리한다", async () => {
    vi.mocked(settingsApi.current).mockResolvedValue({ ...workspace, config: { ...workspace.config, version: 0 }, current: { created_at: null, created_by: null, reason: "플랫폼 기본값", parent_version: null } });
    vi.mocked(settingsApi.history).mockResolvedValue({ ...history, revisions: [] });
    render(<ControlPlaneSettings />);
    expect(await screen.findByText("현재 버전 0")).toBeInTheDocument();
    expect(screen.getByText("저장하면 첫 번째 변경 이력이 기록됩니다.")).toBeInTheDocument();
  });
  it.each(["AUTHENTICATION_REQUIRED", "AUTHORIZATION_DENIED", "VERSION_CONFLICT", "SETTINGS_UNAVAILABLE"])("%s 오류와 요청 ID를 표시하며 Mock으로 대체하지 않는다", async (code) => {
    const fallback = vi.spyOn(mockApi, "getConfigWorkspace");
    vi.mocked(settingsApi.current).mockRejectedValue(new SettingsApiError(code, "서버 설정을 확인해 주세요.", "control-request"));
    render(<ControlPlaneSettings />);
    expect(await screen.findByText(/control-request/)).toBeInTheDocument();
    expect(screen.queryByLabelText("최대 에이전트 반복 횟수")).not.toBeInTheDocument();
    expect(fallback).not.toHaveBeenCalled();
  });
  it("서버 permission과 비활성 사유를 그대로 표시한다", async () => {
    vi.mocked(settingsApi.current).mockResolvedValue({ ...workspace, save_permission: { allowed: false, reason: "감사 계정은 조회만 가능합니다." }, rollback_permission: { allowed: false, reason: "감사 계정은 복원할 수 없습니다." } });
    render(<ControlPlaneSettings />);
    expect(await screen.findByLabelText("최대 에이전트 반복 횟수")).toBeDisabled();
    expect(screen.getByRole("button", { name: "변경 내용 저장" })).toBeDisabled();
    expect(screen.getByText("감사 계정은 조회만 가능합니다.")).toBeVisible();
  });
  it("중복 submit을 막고 네트워크 재시도에는 동일 key를 유지한다", async () => {
    let rejectCommand!: (error: unknown) => void;
    const save = vi.spyOn(settingsApi, "save").mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectCommand = reject; })).mockResolvedValue({ ...workspace, config: { ...workspace.config, version: 2 } });
    render(<ControlPlaneSettings />);
    fireEvent.change(await screen.findByLabelText("최대 에이전트 반복 횟수"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("변경 이유"), { target: { value: "예산 조정" } });
    const form = screen.getByRole("button", { name: "변경 내용 저장" }).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(save).toHaveBeenCalledTimes(1);
    await act(async () => rejectCommand(new SettingsApiError("NETWORK_ERROR", "연결 실패")));
    await screen.findByText("연결 실패");
    fireEvent.submit(form);
    await screen.findByText("설정을 저장했습니다. 현재 버전은 2입니다.");
    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls[0][3]).toBe(save.mock.calls[1][3]);
    expect(save.mock.calls[0][1]).toBe(1);
  });
  it("필드별 validation과 VERSION_CONFLICT 재조회 안내를 표시한다", async () => {
    const save = vi.spyOn(settingsApi, "save").mockRejectedValueOnce(new SettingsApiError("CONFIG_VALIDATION_FAILED", "서버 상한을 확인해 주세요.", "field-request", [{ field: "max_tool_calls", reason: "최대 50입니다." }])).mockRejectedValue(new SettingsApiError("VERSION_CONFLICT", "최신 설정을 다시 불러와 주세요."));
    render(<ControlPlaneSettings />);
    fireEvent.change(await screen.findByLabelText("최대 에이전트 반복 횟수"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("변경 이유"), { target: { value: "변경" } });
    fireEvent.click(screen.getByRole("button", { name: "변경 내용 저장" }));
    expect(await screen.findByText(/최대 도구 호출 횟수: 최대 50/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "변경 내용 저장" }));
    expect(await screen.findByText("최신 설정을 다시 불러와 주세요.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "최신 설정 불러오기" }));
    await waitFor(() => expect(settingsApi.current).toHaveBeenCalledTimes(2));
    expect(save).toHaveBeenCalledTimes(2);
  });
  it("복원 대상·현재 버전·서버 diff와 사유를 전달한다", async () => {
    vi.mocked(settingsApi.current).mockResolvedValue({ ...workspace, config: { ...workspace.config, version: 2 } });
    vi.mocked(settingsApi.history).mockResolvedValue({ ...history, revisions: history.revisions.map((r) => ({ ...r, compared_to_version: 2, rollback_changes: [{ field: "max_tool_calls", before: "10", after: "20" }] })) });
    const rollback = vi.spyOn(settingsApi, "rollback").mockResolvedValue({ ...workspace, config: { ...workspace.config, version: 3 } });
    render(<ControlPlaneSettings />);
    await screen.findByLabelText("최대 에이전트 반복 횟수");
    fireEvent.click(screen.getByText(/^버전 1 ·/));
    expect(screen.getByText("최대 도구 호출 횟수: 10 → 20")).toBeVisible();
    fireEvent.change(screen.getByLabelText("이전 설정을 복원하는 이유"), { target: { value: "안전한 원래 설정 복원" } });
    fireEvent.click(screen.getByRole("button", { name: "버전 1로 복원" }));
    await screen.findByText("버전 1의 설정을 복원하고 새 버전 3으로 기록했습니다.");
    expect(rollback).toHaveBeenCalledWith(1, 2, "안전한 원래 설정 복원", expect.any(String));
  });
});
