import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { Incident, IncidentWorkspace } from "../../contracts/types";
import { mockApi, resetMockState } from "../../shared/mockApi";
import { CreateIncident } from "./CreateIncident";
import { IncidentCommandPanel } from "./IncidentCommandPanel";

const mode = vi.hoisted(() => ({ value: "http" }));
vi.mock("../../shared/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../shared/api")>();
  return { ...actual, get apiMode() { return mode.value; } };
});

beforeEach(() => { resetMockState(); mode.value = "http"; });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function incidentFixture(): Promise<Incident> {
  return { ...(await mockApi.getIncident("inc-1"))!, version: 3, priority: "P1" };
}

async function workspaceFixture(allowed: boolean): Promise<IncidentWorkspace> {
  return {
    ...(await mockApi.getIncidentWorkspace("inc-1"))!,
    commands: { triage: { allowed, reason: allowed ? "분류를 확정할 수 있습니다." : "현재 상태에서는 분류를 다시 확정할 수 없습니다." } },
  };
}

function fillRegistration() {
  fireEvent.change(screen.getByLabelText("제목"), { target: { value: "냉장고 온도 이슈" } });
  fireEvent.change(screen.getByLabelText("매장"), { target: { value: "강남점" } });
  fireEvent.change(screen.getByLabelText("담당자"), { target: { value: "운영 담당자" } });
}

describe("서버 Permission을 따르는 운영 명령", () => {
  it("서버가 거부한 명령은 이유를 표시하고 제출해도 HTTP 요청을 보내지 않는다", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    render(<IncidentCommandPanel incident={await incidentFixture()} workspace={await workspaceFixture(false)} onComplete={vi.fn()} />);
    const button = screen.getByRole("button", { name: "분류 확정" });
    expect(button).toBeDisabled();
    expect(screen.getByText("현재 상태에서는 분류를 다시 확정할 수 없습니다.")).toBeInTheDocument();
    fireEvent.submit(button.closest("form")!);
    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("현재 상태에서는 분류를 다시 확정할 수 없습니다.");
  });

  it("허용된 명령에 expected_version을 전송하고 성공 후 조회를 갱신한다", async () => {
    const incident = await incidentFixture();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ...incident, version: 4, status: "TRIAGED" }));
    vi.stubGlobal("fetch", fetcher);
    const onComplete = vi.fn();
    render(<IncidentCommandPanel incident={incident} workspace={await workspaceFixture(true)} onComplete={onComplete} />);
    fireEvent.click(screen.getByRole("button", { name: "분류 확정" }));
    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce());
    expect(screen.getByRole("status")).toHaveTextContent("분류 확정 요청이 반영되었습니다.");
    expect(fetcher.mock.calls[0][0]).toContain("/incidents/inc-1/triage");
    expect(fetcher.mock.calls[0][1]?.method).toBe("POST");
    expect(JSON.parse(fetcher.mock.calls[0][1]?.body as string)).toEqual({ expected_version: 3, severity: incident.severity });
  });

  it("409 충돌의 요청 ID를 안내하고 사용자가 최신 정보를 조회하게 한다", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code: "CONFLICT", message: "다른 담당자가 수정했습니다. 최신 정보를 확인해 주세요." }, request_id: "req-conflict-ui" }, { status: 409 }));
    vi.stubGlobal("fetch", fetcher);
    const onComplete = vi.fn();
    render(<IncidentCommandPanel incident={await incidentFixture()} workspace={await workspaceFixture(true)} onComplete={onComplete} />);
    fireEvent.click(screen.getByRole("button", { name: "분류 확정" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("다른 담당자가 수정했습니다.");
    expect(screen.getByRole("alert")).toHaveTextContent("req-conflict-ui");
    expect(onComplete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "최신 정보 다시 불러오기" }));
    expect(onComplete).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it("Mock 모드에서는 permission이 허용이어도 실제 명령을 실행하지 않는다", async () => {
    mode.value = "mock";
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    render(<IncidentCommandPanel incident={await incidentFixture()} workspace={await workspaceFixture(true)} onComplete={vi.fn()} />);
    const button = screen.getByRole("button", { name: "분류 확정" });
    expect(button).toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("미리보기에서는 실제 명령을 실행하지 않습니다.");
  });
});

describe("인시던트 등록 팝업", () => {
  it("입력값을 등록하고 서버가 반환한 ID로 상세 화면을 연다", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ...(await incidentFixture()), id: "inc-new", version: 1, priority: "P2" }));
    vi.stubGlobal("fetch", fetcher);
    const onCreated = vi.fn();
    render(<CreateIncident onClose={vi.fn()} onCreated={onCreated} />);
    fillRegistration();
    fireEvent.click(screen.getByRole("button", { name: "등록" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("inc-new"));
    expect(JSON.parse(fetcher.mock.calls[0][1]?.body as string)).toEqual({ title: "냉장고 온도 이슈", store: "강남점", owner: "운영 담당자", severity: "MEDIUM", priority: "P2" });
  });

  it("등록 실패의 요청 ID를 표시하고 입력 내용을 유지한다", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code: "VALIDATION_ERROR", message: "매장 이름을 확인해 주세요." } }, { status: 422, headers: { "X-Request-ID": "req-create-ui" } })));
    const onCreated = vi.fn();
    render(<CreateIncident onClose={vi.fn()} onCreated={onCreated} />);
    fillRegistration();
    fireEvent.click(screen.getByRole("button", { name: "등록" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("매장 이름을 확인해 주세요.");
    expect(screen.getByRole("alert")).toHaveTextContent("req-create-ui");
    expect(screen.getByLabelText("제목")).toHaveValue("냉장고 온도 이슈");
    expect(screen.getByRole("button", { name: "등록" })).toBeEnabled();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("형식이 잘못된 등록 성공 응답으로 상세 화면을 열지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(Response.json({ id: "inc-incomplete" })));
    const onCreated = vi.fn();
    render(<CreateIncident onClose={vi.fn()} onCreated={onCreated} />);
    fillRegistration();
    fireEvent.click(screen.getByRole("button", { name: "등록" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("응답 형식이 현재 화면의 계약과 다릅니다.");
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("Mock 모드의 등록은 비활성화하고 강제 제출도 차단한다", () => {
    mode.value = "mock";
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    render(<CreateIncident onClose={vi.fn()} onCreated={vi.fn()} />);
    fillRegistration();
    const button = screen.getByRole("button", { name: "등록" });
    expect(button).toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
