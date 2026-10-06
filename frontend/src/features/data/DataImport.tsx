import { useRef, useState } from "react";
import { Button } from "../../components/ui";
import { commandKey } from "../../shared/api";
import { confirmImport, previewFile } from "./api";
import type { ImportPreview, ImportReceipt } from "./api";

export function DataImport({ stores, onImported }: { stores: string[]; onImported: (receipt: ImportReceipt) => void }) {
  const [store, setStore] = useState(stores[0] ?? "");
  const [file, setFile] = useState<File>();
  const [kind, setKind] = useState("VOC");
  const [preview, setPreview] = useState<ImportPreview>();
  const [mapping, setMapping] = useState<Record<string, Record<string, string | null>>>({});
  const [dirty, setDirty] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const key = useRef("");
  async function verify() {
    if (!file) return;
    setPending(true); setError(""); setConfirmed(false);
    try {
      if (file.size > 2_000_000) throw new Error("파일 크기는 최대 2MB입니다.");
      const result = await previewFile(file, store, kind, mapping);
      setPreview(result); setDirty(false); key.current = commandKey();
    } catch (e) { setError(e instanceof Error ? e.message : "파일을 확인하지 못했습니다."); } finally { setPending(false); }
  }
  async function commit() {
    if (!preview || !confirmed || dirty) return;
    setPending(true); setError("");
    try { onImported(await confirmImport(preview, key.current)); } catch (e) { setError(e instanceof Error ? e.message : "Import하지 못했습니다."); } finally { setPending(false); }
  }
  function invalidate() { setPreview(undefined); setConfirmed(false); setMapping({}); }
  return <article className="panel"><h2>파일 검증과 미리보기</h2><p>UTF-8 CSV / XLSX, 최대 2MB·합계 1,000행·20열. 오류 행이 하나라도 있으면 저장하지 않습니다. 개인정보·수식·매크로·외부 링크는 제외해 주세요.</p>
    <label>대상 매장 <select value={store} disabled={pending} onChange={(e) => { setStore(e.target.value); invalidate(); }}><option value="">매장 선택</option>{stores.map((s) => <option key={s}>{s}</option>)}</select></label>
    <label>CSV / 일반 Sheet 데이터 종류 <select value={kind} disabled={pending} onChange={(e) => { setKind(e.target.value); invalidate(); }}>{["VOC", "판매_거래", "재고", "매장"].map((s) => <option key={s}>{s}</option>)}</select></label>
    <label>Excel 또는 CSV 파일 <input type="file" accept=".xlsx,.csv" disabled={pending} onChange={(e) => { setFile(e.target.files?.[0]); invalidate(); }} /></label>
    <Button disabled={pending || !file || !store} onClick={verify}>{pending ? "처리 중" : dirty ? "수정한 매핑으로 다시 검증" : "검증 / 미리보기"}</Button>
    {preview && <div><h3>ServIQ가 인식한 데이터</h3><p>아직 canonical 데이터는 저장되지 않았습니다. 미리보기는 15분 후 만료됩니다.</p>
      {preview.sheets.map((sheet) => <section key={sheet.sheet}><h4>{sheet.sheet} → {sheet.kind}</h4><p>총 {sheet.row_count}행 · 정상 {sheet.valid_rows}행 · 오류 위치 {sheet.error_rows}개</p>
        <table><thead><tr><th>업로드 컬럼</th><th>ServIQ 필드</th><th>인식 / 확인</th></tr></thead><tbody>{sheet.mapping.map((m) => <tr key={m.source}><td>{m.source}</td><td><select aria-label={`${sheet.sheet} ${m.source} 매핑`} value={mapping[sheet.sheet]?.[m.source] !== undefined ? mapping[sheet.sheet]?.[m.source] ?? "" : m.target ?? ""} disabled={pending} onChange={(e) => {
          setMapping((old) => ({ ...old, [sheet.sheet]: { ...old[sheet.sheet], [m.source]: e.target.value || null } })); setDirty(true); setConfirmed(false);
        }}><option value="">가져오지 않음</option>{sheet.fields.map((f) => <option key={f.field} value={f.field}>{f.label}</option>)}</select></td><td>{m.warning ?? (m.confidence < 1 ? "별칭 후보 · 확인 필요" : "인식됨 · 확인 필요")} {m.required && "(필수)"}</td></tr>)}</tbody></table>
        <details><summary>저장될 행 미리보기 (최대 5행, VOC 본문 숨김)</summary>{sheet.preview_rows.map((row, i) => <pre key={i}>{JSON.stringify(row, null, 2)}</pre>)}</details>
      </section>)}
      {preview.errors.map((item, i) => <p role="alert" key={i}>{item.location} — {item.message}</p>)}
      {preview.warnings.map((item, i) => <p key={i}>{item.sheet} · {item.column}: {item.message}</p>)}
      <label><input type="checkbox" disabled={!preview.valid || dirty || pending} checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />매핑·대상 매장·미리보기를 확인했습니다.</label>
      <Button disabled={!preview.valid || !confirmed || dirty || pending} onClick={commit}>확인한 데이터 Import</Button>
    </div>}
    {error && <p role="alert">{error}</p>}
  </article>;
}
