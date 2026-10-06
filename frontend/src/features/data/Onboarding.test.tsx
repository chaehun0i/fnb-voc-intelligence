import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { Onboarding } from "./Onboarding";
import * as api from "./api";

vi.mock("./api", () => ({ intakeStatus: vi.fn(), registerStore: vi.fn(), downloadTemplate: vi.fn(), addSample: vi.fn(), initializeRuntime: vi.fn(), startAnalysis: vi.fn(), previewFile: vi.fn(), confirmImport: vi.fn() }));
const status = { stores: ["체험 매장"], first_run: true, has_data: false, can_import: true, analysis_configured: false, can_initialize_runtime: true, checklist: { store: true }, import_count: 0, incident_count: 0, imports: [] };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.intakeStatus).mockResolvedValue(status); });

it("빈 서버 상태에서 세 가지 시작 방법과 체크리스트를 제공합니다", async () => {
  render(<Onboarding />);
  expect(await screen.findByText("ServIQ에 오신 것을 환영합니다")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "내 파일 가져오기" })).toBeInTheDocument();
  expect(screen.getByText("✓ 매장 확인")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "안전한 초기 조사 설정 적용" })).toBeDisabled();
});
it("서버 오류를 Demo로 대체하지 않습니다", async () => {
  vi.mocked(api.intakeStatus).mockRejectedValue(new Error("연결 오류"));
  render(<Onboarding />);
  expect(await screen.findByText("시작 정보를 불러오지 못했습니다")).toBeInTheDocument();
  expect(api.addSample).not.toHaveBeenCalled();
});
it("샘플 내용을 확인한 뒤 실제 API로 준비합니다", async () => {
  vi.mocked(api.addSample).mockResolvedValue({ import_id: "demo", store: "체험 매장", sample: true, row_count: 4, created_at: "", source_refs: [] });
  render(<Onboarding />);
  fireEvent.click(await screen.findByRole("button", { name: "샘플 데이터로 체험하기" }));
  fireEvent.change(screen.getByLabelText("Demo 대상 매장"), { target: { value: "체험 매장" } });
  expect(screen.getByRole("button", { name: "확인 후 샘플 준비" })).toBeDisabled();
  fireEvent.click(screen.getByLabelText("Demo 데이터 추가 내용을 확인했습니다."));
  fireEvent.click(screen.getByRole("button", { name: "확인 후 샘플 준비" }));
  await waitFor(() => expect(api.addSample).toHaveBeenCalledWith("체험 매장", expect.any(String)));
  expect(await screen.findByText("데이터 준비 완료")).toBeInTheDocument();
});
it("기존 데이터는 서버의 연결된 사건으로 바로 이동합니다", async () => {
  vi.mocked(api.intakeStatus).mockResolvedValue({ ...status, has_data: true, first_run: false, imports: [{ import_id: "one", store: "체험 매장", sample: false, row_count: 1, incident_id: "incident-one" }] });
  render(<Onboarding />);
  expect(await screen.findByRole("link", { name: "사건의 근거·RCA·조치안 확인" })).toHaveAttribute("href", "#/incidents?incident=incident-one");
});
it("템플릿은 실제 다운로드 API를 호출합니다", async () => {
  render(<Onboarding />);
  fireEvent.click(await screen.findByRole("button", { name: "엑셀 템플릿으로 시작하기" }));
  fireEvent.click(screen.getByRole("button", { name: "공식 Excel 템플릿 다운로드" }));
  await waitFor(() => expect(api.downloadTemplate).toHaveBeenCalledOnce());
});
