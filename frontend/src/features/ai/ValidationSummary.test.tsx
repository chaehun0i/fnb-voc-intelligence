import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ValidationSummary } from "./ValidationSummary";
import { decodeValidationSummary, getValidationSummary, type ValidationSummary as Summary } from "./validation";
import type { intakeStatus } from "../data/api";
const stores = async () => ({ stores: ["매장"] }) as Awaited<ReturnType<typeof intakeStatus>>;
const summary: Summary = { validation_kind: "USER_OBSERVATION", window: "7d", sessions: 1, completed: 0, abandoned: 1, truncated: false,
  metrics: [{ name: "task_completion_rate", value: 0, sample_size: 1, availability: "INSUFFICIENT_SAMPLE", unit: "ratio", window: "7d" }, { name: "time_to_decision", value: null, sample_size: 0, availability: "UNAVAILABLE", unit: "seconds", window: "7d" }], top_friction: [{ reason: "NO_CLEAR_NEXT_ACTION", count: 1 }] };
it("N과 표본 부족, 실제 0과 측정 불가를 구분하고 마찰을 표시한다", async () => {
  const load = vi.fn(async (_store: string, kind: Summary["validation_kind"]) => ({ ...summary, validation_kind: kind }));
  render(<ValidationSummary load={load} storesLoad={stores} />);
  fireEvent.click(screen.getByRole("button", { name: "사용자 검증 지표 조회" }));
  expect(await screen.findByText(/N=1 · 표본 부족/)).toHaveTextContent("0.0%");
  expect(screen.getByText(/N=0 · 측정 자료 없음/)).toHaveTextContent("측정 불가");
  expect(screen.getByText("다음 행동 불명확 · 1회")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "자료 구분" }), { target: { value: "SYNTHETIC" } });
  expect(await screen.findByText(/Synthetic Validation/)).toHaveTextContent("실제 사용자 검증 결과가 아닙니다");
  expect(load).toHaveBeenCalledWith("매장", "SYNTHETIC");
});
it("권한 실패를 예시 데이터로 대체하지 않는다", async () => {
  render(<ValidationSummary load={async () => { throw new Error("권한 없음"); }} storesLoad={stores} />);
  fireEvent.click(screen.getByRole("button", { name: "사용자 검증 지표 조회" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("권한 없음");
  expect(screen.queryByText(/N=1/)).not.toBeInTheDocument();
});
it("요약 계약은 잘못된 지표와 초과 응답을 거부한다", () => {
  expect(decodeValidationSummary(summary)).toEqual(summary);
  expect(() => decodeValidationSummary({ ...summary, metrics: [{ ...summary.metrics[0], value: -1 }] })).toThrow();
  expect(() => decodeValidationSummary({ ...summary, metrics: Array(15).fill(summary.metrics[0]) })).toThrow();
});
it("서버 자료 구분이 다르면 Synthetic으로 잘못 표시하지 않는다", async () => {
  const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(summary), { status: 200 }));
  try { await expect(getValidationSummary("매장", "SYNTHETIC")).rejects.toThrow("자료 구분"); }
  finally { fetcher.mockRestore(); }
});
