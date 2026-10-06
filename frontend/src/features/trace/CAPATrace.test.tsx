import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { capaFixture } from "../../test/capaFixture";
import { CAPATrace } from "./CAPATrace";

it("실제 CAPA 근거와 기존 Review 연결을 표시한다", () => {
  render(<CAPATrace run={capaFixture} />);
  expect(screen.getByText("승인 대기 — 사람의 검토가 필요합니다")).toBeInTheDocument();
  expect(screen.getByText(capaFixture.capa_proposals![0].verification_criteria)).toBeInTheDocument();
  expect(screen.getByText("review:r2")).toBeInTheDocument();
  expect(screen.getByRole("link")).toHaveAttribute("href", "#/reviews?approval=approval-1");
});

it("승인과 실행 완료를 구분하고 실제 반려를 표시한다", () => {
  const approved = { ...capaFixture, approval: { ...capaFixture.approval!, status: "APPROVED" as const, phase: "READY_TO_EXECUTE" as const } };
  const view = render(<CAPATrace run={approved} />);
  expect(screen.getByText("승인 완료 — 실행 단계 대기")).toBeInTheDocument();
  expect(screen.queryByText("실행 완료")).not.toBeInTheDocument();
  view.rerender(<CAPATrace run={{ ...approved, approval: { ...approved.approval, status: "REJECTED", phase: "REJECTED" } }} />);
  expect(screen.getByText("조치안 반려")).toBeInTheDocument();
});
