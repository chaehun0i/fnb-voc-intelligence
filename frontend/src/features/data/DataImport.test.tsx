import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { DataImport } from "./DataImport";
import * as api from "./api";

vi.mock("./api", () => ({ previewFile: vi.fn(), confirmImport: vi.fn() }));
const preview: api.ImportPreview = { preview_id: "preview-one", digest: "a".repeat(64), store: "매장", valid: true, row_count: 1, expires_at: "2099-01-01", errors: [], warnings: [], sheets: [{ sheet: "VOC", kind: "VOC", row_count: 1, valid_rows: 1, error_rows: 0, fields: [{ field: "text", label: "VOC 내용" }], mapping: [{ source: "의견", target: "text", confidence: .9, inferred_type: "text", required: true, warning: null }], preview_rows: [{ text: "본문 숨김" }] }] };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.previewFile).mockResolvedValue(preview); });
async function ready() {
  fireEvent.change(screen.getByLabelText("대상 매장"), { target: { value: "매장" } });
  fireEvent.change(screen.getByLabelText("Excel 또는 CSV 파일"), { target: { files: [new File(["csv"], "input.csv", { type: "text/csv" })] } });
  fireEvent.click(screen.getByRole("button", { name: "검증 / 미리보기" }));
  await screen.findByText("ServIQ가 인식한 데이터");
}
it("미리보기는 저장하지 않으며 확인한 경우만 Import합니다", async () => {
  const imported = vi.fn();
  vi.mocked(api.confirmImport).mockResolvedValue({ import_id: "import", store: "매장", sample: false, row_count: 1, created_at: "", source_refs: [] });
  render(<DataImport stores={["매장"]} onImported={imported} />);
  await ready();
  expect(api.confirmImport).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "확인한 데이터 Import" })).toBeDisabled();
  fireEvent.click(screen.getByLabelText("매핑·대상 매장·미리보기를 확인했습니다."));
  fireEvent.click(screen.getByRole("button", { name: "확인한 데이터 Import" }));
  await waitFor(() => expect(imported).toHaveBeenCalledOnce());
});
it("매핑 변경은 재검증 전 저장할 수 없습니다", async () => {
  render(<DataImport stores={["매장"]} onImported={vi.fn()} />);
  await ready();
  fireEvent.change(screen.getByLabelText("VOC 의견 매핑"), { target: { value: "" } });
  expect(screen.getByRole("button", { name: "확인한 데이터 Import" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "수정한 매핑으로 다시 검증" })).toBeInTheDocument();
});
it("검증 오류는 표시하고 Mock Import를 만들지 않습니다", async () => {
  vi.mocked(api.previewFile).mockResolvedValue({ ...preview, valid: false, errors: [{ location: "VOC!C8", code: "INVALID_VALUE", message: "내용을 확인해 주세요." }] });
  render(<DataImport stores={["매장"]} onImported={vi.fn()} />);
  await ready();
  expect(screen.getByRole("alert")).toHaveTextContent("VOC!C8");
  expect(screen.getByRole("button", { name: "확인한 데이터 Import" })).toBeDisabled();
  expect(api.confirmImport).not.toHaveBeenCalled();
});
