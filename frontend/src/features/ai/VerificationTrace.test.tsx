import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { verificationFixture } from "../../test/verificationFixture";
import { CAPATrace } from "./CAPATrace";
import { VerificationTrace } from "./VerificationTrace";

it.each(["PASS", "FAIL", "INCONCLUSIVE"] as const)("서버의 %s와 내부 시뮬레이션 범위를 표시한다", (result) => {
  const run = verificationFixture(result);
  render(<VerificationTrace run={run} />);
  expect(screen.getByText(run.resulting_incident_status!)).toBeInTheDocument();
  expect(screen.getByText(/실제 현장 조치의 효과를 입증하지 않습니다/)).toBeInTheDocument();
  expect(screen.getByText("INTERNAL_RECORD_ONLY / SUCCEEDED")).toBeInTheDocument();
  expect(screen.getByText(run.verification_evidence![0].source_ref)).toBeInTheDocument();
});
it("승인 대기와 내부 실행 기록을 구분한다", () => {
  render(<CAPATrace run={verificationFixture("PASS")} />);
  expect(screen.getByText("승인 완료 — 내부 실행 기록됨 (외부 변경 없음)")).toBeInTheDocument();
  expect(screen.queryByText("승인 완료 — 실행 단계 대기")).not.toBeInTheDocument();
});
