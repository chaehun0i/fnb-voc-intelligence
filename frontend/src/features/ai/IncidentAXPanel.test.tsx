import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { IncidentAXPanel } from "./IncidentAXPanel";
import { decodeAX, getIncidentAX, type IncidentAX } from "./ax";
import { agentRunApi } from "./api";

export const axFixture: IncidentAX = {
  schema_version: "incident-ax-1", incident_id: "i", current_phase: "PENDING_APPROVAL",
  brief: { headline: "사람의 승인 대기", summary: "근거 2개를 확인했습니다. 조치안 검토가 필요합니다.", primary_hypothesis: null, confidence_level: "MEDIUM" },
  coverage: { confirmed: ["HISTORY"], missing: ["INVENTORY"], conflicting: [], stale: [], evidence_count: 2 },
  uncertainties: ["원인 확정 아님"], human_action: "APPROVAL_REQUIRED",
  next_action: { action_type: "OPEN_REVIEW", label: "조치안 승인 검토", reason: "승인 완료는 실행 완료가 아닙니다.", risk: "HIGH", permission: true, requires_approval: true, blocking_reason: null, alternative_actions: ["CHECK_RESULT"] },
  progress: [{ agent_type: "HISTORY", label: "과거 사례 조사", status: "SUCCESS", evidence_count: 2 }],
  verification_result: null, execution_mode: null, approval_status: "PENDING", source_run_id: "run", manifest_reference: null, decision_reference: "decision",
  explanation: { supporting_refs: ["review:r1"], contradicting_refs: [], missing_codes: ["CAPABILITY_UNAVAILABLE"], assumptions: ["입력된 관측 자료"], cannot_verify: ["현장 개선 효과 미검증"], technical_trace_available: true },
  updated_at: "2026-10-07T00:00:00Z",
};
it("AX는 업무 결과와 다음 행동을 표시하고 기술 상세는 선택해서 연다", async () => {
  const action = vi.fn();
  render(<IncidentAXPanel incidentId="i" load={async () => axFixture} onAction={action} />);
  expect(screen.getByText("AI 업무 요약을 불러오는 중입니다")).toBeInTheDocument();
  expect(await screen.findByText("사람의 승인 대기")).toBeInTheDocument();
  expect(screen.getByText("부족: 재고")).toBeInTheDocument();
  expect(screen.getByText(/과거 사례 조사 · 확인 완료/)).toBeInTheDocument();
  expect(screen.getByText("원인 확정 아님")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "조치안 승인 검토" }));
  expect(action).toHaveBeenCalledWith("OPEN_REVIEW");
  expect(screen.getByText("판단 근거와 한계 확인").closest("details")).not.toHaveAttribute("open");
});
it("서버 권한을 사용하며 오류를 예시 결과로 대체하지 않는다", async () => {
  const { unmount } = render(<IncidentAXPanel incidentId="i" load={async () => ({ ...axFixture, next_action: { ...axFixture.next_action, permission: false } })} onAction={vi.fn()} />);
  expect(await screen.findByRole("button", { name: "조치안 승인 검토" })).toBeDisabled(); unmount();
  render(<IncidentAXPanel incidentId="i" load={async () => { throw new Error("접근 불가"); }} onAction={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("접근 불가");
  expect(screen.queryByText("사람의 승인 대기")).not.toBeInTheDocument();
});
it.each(["PASS", "FAIL", "INCONCLUSIVE"] as const)("검증 %s와 내부 실행 의미를 유지한다", async (result) => {
  render(<IncidentAXPanel incidentId="i" load={async () => ({ ...axFixture, verification_result: result, execution_mode: "INTERNAL_RECORD_ONLY" })} onAction={vi.fn()} />);
  expect(await screen.findByText("내부 실행 기록 · 외부 시스템 변경 없음")).toBeInTheDocument();
  expect(screen.getByText(/^검증:/)).toHaveTextContent({ PASS: "검증 기준 충족", FAIL: "검증 실패", INCONCLUSIVE: "판정 보류" }[result]);
});
it("AX HTTP contract와 실패를 명시적으로 검증한다", async () => {
  expect(decodeAX(axFixture)).toEqual(axFixture);
  expect(() => decodeAX({ ...axFixture, brief: { ...axFixture.brief, confidence_level: .99 } })).toThrow();
  await expect(getIncidentAX("i", vi.fn().mockResolvedValue(new Response("{}", { status: 403 })))).rejects.toThrow("권한");
  await expect(getIncidentAX("i", vi.fn().mockRejectedValue(new Error("raw secret")))).rejects.toThrow("연결하지 못했습니다");
});

it("AX에서 기존 서버 제어 명령과 버전을 사용하고 결과를 새로 조회한다", async () => {
  const control = vi.fn().mockResolvedValue(undefined);
  const previous = agentRunApi.control;
  agentRunApi.control = control;
  try {
    const load = vi.fn().mockResolvedValue({ ...axFixture, runtime: {
      control_status: "RUNNING", control_version: 3, termination_reason: null, message: "자료 조사 중",
      budget_summary: "읽기 조사 2 / 20회", remaining_operations: 18, new_evidence: false,
      human_action: "담당자가 근거를 확인해 주세요.", permissions: { pause: true, resume: false, stop: true, takeover: true }, versions: { loop: "bounded-investigation-1" },
    } });
    render(<IncidentAXPanel incidentId="i" load={load} onAction={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "일시정지" }));
    expect(await screen.findByRole("button", { name: "자동 조사 재개" })).toBeDisabled();
    expect(control).toHaveBeenCalledWith("i", "run", "pause", 3, expect.any(String));
  } finally { agentRunApi.control = previous; }
});

it("RAW 의견은 승인과 구분하며 측정 불가 지표를 숫자로 꾸미지 않는다", async () => {
  const record = vi.fn().mockResolvedValue(undefined);
  render(<IncidentAXPanel incidentId="i" load={async () => ({ ...axFixture, feedback_allowed: true,
    metrics: [{ name: "time_to_first_useful_evidence", status: "UNAVAILABLE", value: null, unit: "seconds" }] })} record={record} onAction={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "수정 필요 의견" }));
  expect(await screen.findByText("의견을 기록했습니다. 승인이나 조치 실행은 변경하지 않았습니다.")).toBeInTheDocument();
  expect(record).toHaveBeenCalledWith("i", "recommendation_edited", expect.any(String));
  expect(screen.getByText(/측정 불가/)).toBeInTheDocument();
  expect(record).toHaveBeenCalledWith("i", "ai_brief_viewed", expect.any(String));
});
