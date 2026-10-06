import { apiBaseUrl, authHeaders, commandKey } from "../../shared/api";

export type IntakeStatus = { stores: string[]; has_data: boolean; first_run: boolean; can_import: boolean; import_count: number; incident_count: number; imports: Array<{ import_id: string; store: string; sample: boolean; row_count: number; incident_id?: string }> };
export async function dataRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}/data${path}`, { ...init, headers: { ...authHeaders(), ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? `데이터 요청에 실패했습니다 (${response.status}).`);
  }
  return response.json();
}
export const intakeStatus = async () => {
  const value = await dataRequest<IntakeStatus>("/onboarding");
  if (!Array.isArray(value.stores) || value.stores.some((s) => typeof s !== "string") || typeof value.first_run !== "boolean" || typeof value.has_data !== "boolean" || typeof value.can_import !== "boolean" || !Array.isArray(value.imports)) throw new Error("데이터 상태 응답 형식을 확인해 주세요.");
  return value;
};
export const registerStore = (store: string) => dataRequest<{ store: string }>("/stores", { method: "POST", headers: { "Idempotency-Key": commandKey() }, body: JSON.stringify({ store }) });
export const addSample = (store: string, key: string) => dataRequest<ImportReceipt>("/sample", { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ store, confirmed: true }) });
export async function downloadTemplate() {
  const response = await fetch(`${apiBaseUrl}/data/template`, { headers: authHeaders() });
  if (!response.ok) throw new Error("템플릿을 다운로드하지 못했습니다. 인증과 연결을 확인해 주세요.");
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = "ServIQ-template-v1.xlsx"; anchor.click();
  URL.revokeObjectURL(url);
}

export type ImportReceipt = { import_id: string; store: string; sample: boolean; row_count: number; created_at: string; source_refs: Array<{ source_ref: string; agent_type: string }> };
export type ImportPreview = { preview_id: string; digest: string; store: string; valid: boolean; row_count: number; expires_at: string;
  sheets: Array<{ sheet: string; kind: string; row_count: number; valid_rows: number; error_rows: number; fields: Array<{ field: string; label: string }>; mapping: Array<{ source: string; target: string | null; confidence: number; inferred_type: string; required: boolean; warning: string | null }>; preview_rows: Array<Record<string, string | number>> }>;
  errors: Array<{ location: string; code: string; message: string }>; warnings: Array<{ sheet: string; column: string; message: string }> };
export async function previewFile(file: File, store: string, kind: string, mappings: Record<string, Record<string, string | null>>) {
  const body = new FormData(); body.set("file", file); body.set("store", store); body.set("kind", kind); body.set("mappings", JSON.stringify(mappings));
  const value = await dataRequest<ImportPreview>("/preview", { method: "POST", body });
  if (typeof value.valid !== "boolean" || !Array.isArray(value.sheets) || !Array.isArray(value.errors) || !Array.isArray(value.warnings) || typeof value.preview_id !== "string" || typeof value.digest !== "string") throw new Error("미리보기 응답 형식을 확인해 주세요.");
  return value;
}
export const confirmImport = (preview: ImportPreview, key: string) => dataRequest<ImportReceipt>(`/imports/${encodeURIComponent(preview.preview_id)}/confirm`, {
  method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ digest: preview.digest, confirmed: true }),
});
