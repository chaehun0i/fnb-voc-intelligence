import { useState } from "react";
import { Button, PageHeading, StateMessage } from "../../components/ui";
import { useQuery } from "../../lib/useQuery";
import { addSample, downloadTemplate, initializeRuntime, intakeStatus, registerStore, startAnalysis } from "./api";
import { apiMode, commandKey } from "../../shared/api";
import type { ImportReceipt } from "./api";
import { DataImport } from "./DataImport";

export function Onboarding() {
  if (apiMode !== "http") return <StateMessage kind="empty" title="실제 데이터 입력은 HTTP 모드에서 사용합니다">예시 화면에서는 운영 데이터를 생성하지 않습니다. Compose 콘솔 또는 VITE_API_MODE=http로 연결한 화면을 사용해 주세요.</StateMessage>;
  return <OnboardingHttp />;
}

function OnboardingHttp() {
  const query = useQuery(intakeStatus);
  const [store, setStore] = useState("");
  const [choice, setChoice] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<ImportReceipt>();
  const [sampleStore, setSampleStore] = useState("");
  const [sampleConfirmed, setSampleConfirmed] = useState(false);
  const [sampleKeys] = useState(() => new Map<string, string>());
  const [topic, setTopic] = useState("품질");
  const [consent, setConsent] = useState(false);
  const [analysisKey] = useState(commandKey);
  const [initKey] = useState(commandKey);
  async function initialize() {
    setPending(true); setError("");
    try { await initializeRuntime(initKey); query.reload(); } catch (e) { setError(e instanceof Error ? e.message : "설정 실패"); } finally { setPending(false); }
  }
  async function analyze(id: string) {
    setPending(true); setError("");
    try { const result = await startAnalysis(id, topic, `${analysisKey}:${id}`); window.location.hash = `/incidents?incident=${encodeURIComponent(result.incident_id)}`; } catch (e) { setError(e instanceof Error ? e.message : "조사 시작 실패"); } finally { setPending(false); }
  }
  async function sample() {
    setPending(true); setError("");
    const key = sampleKeys.get(sampleStore) ?? commandKey(); sampleKeys.set(sampleStore, key);
    try { setReceipt(await addSample(sampleStore, key)); query.reload(); } catch (e) { setError(e instanceof Error ? e.message : "샘플 준비 실패"); } finally { setPending(false); }
  }
  async function saveStore() {
    setPending(true); setError("");
    try { await registerStore(store); query.reload(); } catch (e) { setError(e instanceof Error ? e.message : "매장을 등록하지 못했습니다."); } finally { setPending(false); }
  }
  async function template() {
    setPending(true); setError("");
    try { await downloadTemplate(); } catch (e) { setError(e instanceof Error ? e.message : "다운로드 실패"); } finally { setPending(false); }
  }
  if (query.loading) return <StateMessage kind="loading" title="매장과 데이터 상태를 확인하고 있습니다" />;
  if (query.error || !query.data) return <StateMessage kind="error" title="시작 정보를 불러오지 못했습니다" onRetry={query.reload}>{query.error}</StateMessage>;
  const status = query.data;
  return <section className="page"><PageHeading title="ServIQ에 오신 것을 환영합니다" description="매장의 VOC와 운영 데이터를 연결하면 문제를 확인하고, 근거를 조사하고, 필요한 조치를 제안할 수 있습니다." />
    <p>매장 확인 → 데이터 준비 → 사건 확인 → 조사 결과 확인</p>
    <article className="panel"><h2>1. 매장 확인</h2><p>{status.stores.length ? `등록된 매장: ${status.stores.join(", ")}` : "아직 등록된 매장이 없습니다. 현재 권한으로 관리할 매장명을 입력해 주세요."}</p>
      {status.can_import && <div><label>매장명 <input value={store} maxLength={100} onChange={(e) => setStore(e.target.value)} /></label><Button disabled={pending || !store.trim()} onClick={saveStore}>매장 등록</Button></div>}
    </article>
    {receipt && <article className="panel"><h2>데이터 준비 완료</h2><p>{receipt.store} · {receipt.row_count}건 저장했습니다. 다음으로 Incident를 확인하거나 등록해 주세요.</p><a href="#/incidents">첫 Incident 확인하기</a></article>}
    <article className="panel"><h2>2. 시작 방법 선택</h2>
      <Button onClick={() => setChoice("sample")}>샘플 데이터로 체험하기</Button><p>개인정보 없는 작은 Demo 시나리오로 조사 흐름을 체험합니다.</p>
      <Button onClick={() => setChoice("template")}>엑셀 템플릿으로 시작하기</Button><p>지원 컬럼과 예시를 확인하고 운영 데이터를 작성합니다.</p>
      <Button onClick={() => setChoice("file")}>내 파일 가져오기</Button><p>Excel/CSV의 컬럼을 확인하고 검증·미리보기 후 저장합니다.</p>
      {choice && <p role="status">선택한 방법: {{ sample: "샘플 데이터", template: "엑셀 템플릿", file: "내 파일" }[choice]} · 먼저 대상 매장을 확인해 주세요.</p>}
      {choice === "template" && <><p>매장·VOC·판매_거래·재고 Sheet와 입력가이드를 제공합니다. 거래·재고는 관측 자료 입력이며 POS/ERP 연결이 아닙니다.</p><Button disabled={pending} onClick={template}>공식 Excel 템플릿 다운로드</Button></>}
      {choice === "sample" && status.can_import && <div><label>Demo 대상 매장 <select value={sampleStore} onChange={(e) => { setSampleStore(e.target.value); setSampleConfirmed(false); }}><option value="">매장 선택</option>{status.stores.map((s) => <option key={s}>{s}</option>)}</select></label>
        <p>운영 자료가 없는 별도의 체험 매장을 선택해 주세요. Demo VOC 2건, 환불 관측 1건, 재고 부족 관측 1건을 추가합니다. 실제 개인정보나 POS/ERP 연결은 없습니다. Demo와 운영 파일은 같은 매장에 혼합하지 않으며 같은 매장의 Demo는 한 번만 생성됩니다.</p>
        <label><input type="checkbox" checked={sampleConfirmed} onChange={(e) => setSampleConfirmed(e.target.checked)} />Demo 데이터 추가 내용을 확인했습니다.</label>
        <Button disabled={pending || !sampleStore || !sampleConfirmed} onClick={sample}>확인 후 샘플 준비</Button></div>}
    </article>
    {status.can_import && (choice === "file" || choice === "template") && <DataImport stores={status.stores} onImported={(value) => { setReceipt(value); query.reload(); }} />}
    <article className="panel"><h2>3. ServIQ 시작 체크리스트</h2>
      <ul>{[["store", "매장 확인"], ["data", "데이터 준비"], ["incident", "첫 사건 확인"], ["investigation", "AI 조사 실행"], ["results", "근거와 조사 결과 확인"]].map(([key, label]) => <li key={key}>{status.checklist?.[key] ? "✓" : "○"} {label}</li>)}</ul>
      {!status.analysis_configured && <><p>조사 실행은 서버 운영 정책이 허용해야 합니다. 기존 설정은 자동으로 변경하지 않습니다.</p><a href="#/settings">운영 설정 확인</a></>}
      {status.can_initialize_runtime && <><p>관리자 초기 체험 설정: Jev·제한 조사·RCA/CAPA 제안을 허용합니다. 외부 AI 전송, 외부 시스템 변경, 내부 실행은 허용하지 않으며 사람의 승인 정책은 유지합니다.</p>
        <label><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />조직 초기 조사 설정에 동의합니다.</label><Button disabled={pending || !consent} onClick={initialize}>안전한 초기 조사 설정 적용</Button></>}
      {status.imports.length > 0 && <><label>조사할 VOC 검색어 <input value={topic} maxLength={100} onChange={(e) => setTopic(e.target.value)} /></label><p>가져온 VOC에 포함된 짧은 주제로 조사합니다. 개인정보나 원문 전체를 입력하지 마세요. 거래/재고 관측은 POS/ERP 연결이 아닙니다.</p>
        {status.imports.map((i) => <div key={i.import_id}><p>{i.sample ? "Demo" : "파일 입력"} · {i.store} · {i.row_count}건</p>{i.incident_id ? <a href={`#/incidents?incident=${encodeURIComponent(i.incident_id)}`}>사건의 근거·RCA·조치안 확인</a> : status.can_import && <Button disabled={pending || !status.analysis_configured || topic.trim().length < 2} onClick={() => analyze(i.import_id)}>이 자료로 첫 조사 시작</Button>}</div>)}
        <p>Worker가 조사를 처리하면 사건 상세의 실제 Agent 조사에서 근거·부족한 자료·RCA·CAPA를 확인합니다. 승인과 실행은 별개이며 외부 시스템은 변경하지 않습니다.</p></>}
    </article>
    {error && <p role="alert">{error}</p>}
    <a href="#/dashboard">Dashboard 보기</a> · <a href="#/incidents">Incident 보기</a>
    {status.has_data && <p>기존 데이터가 있습니다. 데이터 입력을 건너뛰고 업무를 계속할 수 있습니다.</p>}
  </section>;
}
