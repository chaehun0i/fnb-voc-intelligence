import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "../../components/ui";
import { intakeStatus } from "../data/api";
import { validationApi, type ValidationScenario, type ValidationSignal, type ValidationView } from "./validation";

const locatorKey = "serviq-validation-session"; // Locator only; all state/completion comes from the server.
type ContextValue = { active: boolean; signal: (body: ValidationSignal, key?: string) => Promise<void> };
const ValidationContext = createContext<ContextValue>({ active: false, signal: async () => {} });
export const useValidation = () => useContext(ValidationContext);
export function ValidationMode({ children, route, incidentId, api = validationApi }: { children: ReactNode; route: string; incidentId?: string; api?: typeof validationApi }) {
  const [id, setId] = useState<string | null>(() => sessionStorage.getItem(locatorKey));
  const [view, setView] = useState<ValidationView | null>(null);
  const [setup, setSetup] = useState(false);
  const [stores, setStores] = useState<string[]>([]);
  const [store, setStore] = useState("");
  const [scenario, setScenario] = useState<ValidationScenario>("happy_path");
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const startKey = useRef(crypto.randomUUID());
  const refresh = useCallback(async () => { if (id) setView(await api.get(id)); }, [api, id]);
  useEffect(() => { if (id) void refresh().catch(() => setError("검증 기록을 불러오지 못했습니다. 권한과 연결을 확인한 뒤 다시 조회해 주세요.")); }, [id, refresh]);
  const active = view?.session.status === "ACTIVE";
  const signal = useCallback(async (body: ValidationSignal, key?: string) => {
    if (!active || !id) return;
    const eventKey = key ?? (body.milestone ? `${id}:${body.milestone}:${body.incident_id ?? view?.session.incident_id ?? ""}` : crypto.randomUUID());
    try { await api.signal(id, body, eventKey); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "검증 관찰을 저장하지 못했습니다."); throw e; }
  }, [active, id, api, refresh, view?.session.incident_id]);
  useEffect(() => {
    if (!active) return;
    const body: ValidationSignal | null = incidentId ? { milestone: "INCIDENT_OPENED", surface: "INCIDENT", incident_id: incidentId } : route === "onboarding" ? { milestone: "ONBOARDING_STARTED", surface: "ONBOARDING" } : route === "reviews" && view?.session.incident_id ? { milestone: "REVIEW_OPENED", surface: "REVIEW" } : null;
    if (body) void signal(body).catch(() => {});
    void intakeStatus().then((status) => { if (status.has_data) return signal({ milestone: "DATA_READY", surface: "ONBOARDING" }); }).catch(() => {});
  }, [active, incidentId, route, signal, view?.session.incident_id]);
  async function execute(action: () => Promise<void>) {
    if (pending) return;
    setPending(true); setError("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "검증 요청에 실패했습니다."); }
    finally { setPending(false); }
  }
  return <ValidationContext.Provider value={{ active, signal }}>
    <section className="mx-4 mt-4 rounded-lg border border-slate-200 p-3" aria-label="사용자 과업 검증">
      {!id && !setup && <Button onClick={() => void execute(async () => { const status = await intakeStatus(); setStores(status.stores); setStore(status.stores[0] ?? ""); setSetup(true); })}>사용자 과업 검증 참여</Button>}
      {setup && !id && <div className="space-y-3"><h2>사용자 과업 검증 시작</h2><p>업무 수행 과정의 단계·소요 시간·선택형 의견만 수집합니다. 이름, 원문 자료, 자유 입력 내용은 수집하지 않습니다. 참여 후 언제든 중단할 수 있습니다.</p>
        {!stores.length ? <p>데이터 입력 화면에서 먼저 매장을 확인해 주세요.</p> : <label>검증 매장 <select value={store} onChange={(e) => { setStore(e.target.value); startKey.current = crypto.randomUUID(); }}>{stores.map((s) => <option key={s}>{s}</option>)}</select></label>}
        <label>관찰 과업 <select value={scenario} onChange={(e) => { setScenario(e.target.value as ValidationScenario); startKey.current = crypto.randomUUID(); }}>{Object.entries({ happy_path: "사건 판단과 결과 확인", more_evidence: "근거 충분성 판단", reopen: "재조사 사건 판단", manual_takeover: "담당자 인계 판단", abandon: "자유 탐색" }).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>
        <label className="block"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> 업무 과정의 제한된 관찰 기록에 동의합니다.</label>
        <Button disabled={pending || !store || !consent} onClick={() => void execute(async () => { const s = await api.start(store, scenario, startKey.current); sessionStorage.setItem(locatorKey, s.session_id); setId(s.session_id); setSetup(false); })}>과업 시작</Button><Button onClick={() => setSetup(false)}>취소</Button>
      </div>}
      {id && !view && <p>서버의 검증 상태를 확인하는 중입니다.</p>}
      {view && <div className="space-y-2"><h2>{view.session.validation_kind === "SYNTHETIC" ? "Synthetic 검증 · 실제 사용자 관찰 아님" : "사용자 과업 관찰"}</h2><p>{view.task.business_goal}</p><p>기록 상태: {view.session.status === "ACTIVE" ? "관찰 중" : view.session.status === "COMPLETED" ? "과업 완료 확인" : "과업 중단"} · 관측 단계 {view.journey.milestones.length}개</p>
        {active && <div className="flex flex-wrap gap-2"><Button disabled={pending} onClick={() => void execute(async () => { await api.finish(id!, `${id}:complete`); await refresh(); })}>과업 완료 확인</Button>
          <Button disabled={pending} onClick={() => void execute(() => signal({ surface: "INCIDENT", friction: "NO_CLEAR_NEXT_ACTION", safe_reason_code: "NOT_CLEAR" }))}>다음 행동이 불명확함</Button>
          <Button disabled={pending} onClick={() => void execute(() => signal({ surface: "INCIDENT", friction: "TASK_ABANDONED", safe_reason_code: "USER_CHOICE" }, `${id}:abandon`))}>과업 중단</Button></div>}
        {!active && <Button onClick={() => { sessionStorage.removeItem(locatorKey); setId(null); setView(null); startKey.current = crypto.randomUUID(); }}>검증 모드 닫기</Button>}
      </div>}
      {error && <div role="alert"><p>{error}</p><Button disabled={pending} onClick={() => void execute(refresh)}>검증 상태 다시 조회</Button>{id && !view && <Button onClick={() => { sessionStorage.removeItem(locatorKey); setId(null); setError(""); }}>연결된 검증 모드 닫기</Button>}</div>}
    </section>{children}
  </ValidationContext.Provider>;
}
