import { useMemo, useState } from "react";
import { Button, StateMessage } from "../../components/ui";
import { useQuery } from "../../lib/useQuery";
import { intakeStatus } from "../data/api";
import { getValidationSummary, type ValidationSummary as Summary } from "./validation";

const labels: Record<string, string> = { task_completion_rate: "과업 완료율", time_to_first_useful_evidence: "첫 유효 근거까지", time_to_human_action: "사람 행동 안내까지", time_to_decision: "업무 결정까지", human_intervention_rate: "사람 개입률", accept_rate: "수용 의견", edit_rate: "수정 필요 의견", reject_rate: "비수용 의견", request_more_evidence_rate: "추가 근거 요청 의견", manual_takeover_rate: "수동 인계율", loop_abort_rate: "자동 조사 종료율", end_to_end_completion_rate: "전체 흐름 완료율", median_task_duration: "완료 과업 소요 시간 중앙값", cost_per_completed_incident: "완료 실행의 추정 비용" };
const availability = { AVAILABLE: "관측 가능", PARTIAL: "일부 관측", INSUFFICIENT_SAMPLE: "표본 부족", UNAVAILABLE: "측정 자료 없음" };
const friction: Record<string, string> = { BACKTRACK: "이전 단계로 돌아감", REPEATED_ACTION: "같은 행동 반복", HELP_OPENED: "도움말 확인", EXPLANATION_EXPANDED: "판단 설명 펼침", MANUAL_TAKEOVER: "담당자 인계", ACTION_REJECTED: "제안 비수용", REQUEST_MORE_EVIDENCE: "추가 근거 필요", TASK_ABANDONED: "과업 중단", ERROR_RECOVERED: "오류 후 회복", NO_CLEAR_NEXT_ACTION: "다음 행동 불명확" };

function SummaryData({ store, kind, load }: { store: string; kind: Summary["validation_kind"]; load: typeof getValidationSummary }) {
  const loader = useMemo(() => () => load(store, kind), [store, kind, load]);
  const query = useQuery(loader);
  if (query.loading) return <StateMessage kind="loading" title="사용자 과업 지표를 불러오는 중입니다" />;
  if (query.error) return <StateMessage kind="error" title="검증 요약을 조회하지 못했습니다" onRetry={query.reload}>{query.error}</StateMessage>;
  const v = query.data;
  if (!v) return null;
  return <div className="space-y-3"><p>최근 7일 · 시작 {v.sessions} · 완료 {v.completed} · 중단 {v.abandoned}</p><Button onClick={query.reload}>검증 지표 새로고침</Button>
    {v.validation_kind === "SYNTHETIC" ? <p className="preview-notice">Synthetic Validation · 실제 사용자 검증 결과가 아닙니다.</p> : <p>참여 관찰 기록만 집계합니다. 표본 수는 고유 사용자 수나 통계적 유의성을 뜻하지 않습니다.</p>}
    {!v.sessions && <p>관측된 검증 과업이 없습니다. 측정 자료 없음은 0%와 다릅니다.</p>}
    {v.sessions > 0 && v.sessions < 5 && <p>표본이 부족합니다. 개별 과업의 막힌 지점을 확인하는 참고 자료로 사용해 주세요.</p>}
    {v.truncated && <p>조회 한도에 도달해 일부 자료만 집계했습니다.</p>}
    <dl className="grid gap-3 sm:grid-cols-2">{v.metrics.map((m) => <div key={m.name}><dt>{labels[m.name] ?? "기타 관측 지표"}</dt><dd>{m.value === null ? "측정 불가" : m.unit === "ratio" ? `${(m.value * 100).toFixed(1)}%` : `${m.value.toFixed(2)} ${m.unit === "seconds" ? "초" : "USD (추정)"}`} · N={m.sample_size} · {availability[m.availability]}</dd></div>)}</dl>
    <h3>사용자가 어디에서 막혔는가?</h3><p>설명 펼침·도움말 확인은 탐색 신호이며, 그 자체로 실패를 의미하지 않습니다.</p>
    {v.top_friction.length ? <ul>{v.top_friction.map((f) => <li key={f.reason}>{friction[f.reason] ?? "기타 제한된 관측"} · {f.count}회</li>)}</ul> : <p>기록된 마찰 신호가 없습니다. 문제가 없다는 결론은 아닙니다.</p>}
  </div>;
}
export function ValidationSummary({ load = getValidationSummary, storesLoad = intakeStatus }: { load?: typeof getValidationSummary; storesLoad?: typeof intakeStatus }) {
  const [opened, setOpened] = useState(false);
  const [stores, setStores] = useState<string[]>([]);
  const [store, setStore] = useState("");
  const [kind, setKind] = useState<Summary["validation_kind"]>("USER_OBSERVATION");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  async function open() {
    setPending(true); setError("");
    try { const s = await storesLoad(); setStores(s.stores); setStore(s.stores[0] ?? ""); setOpened(true); }
    catch { setError("검증 매장 정보를 조회하지 못했습니다. 권한과 연결을 확인해 주세요."); }
    finally { setPending(false); }
  }
  return <article className="panel !min-h-0" aria-label="사용자 검증 요약"><h2>User Validation · AX Friction</h2><p>업무 과업의 완료와 막힌 지점을 확인합니다. 관리자에게 허용된 매장 범위만 조회됩니다.</p>
    {!opened && <Button disabled={pending} onClick={() => void open()}>사용자 검증 지표 조회</Button>}
    {error && <p role="alert">{error}</p>}
    {opened && <><label>조회 매장 <select value={store} onChange={(e) => setStore(e.target.value)}>{stores.map((s) => <option key={s}>{s}</option>)}</select></label> <label>자료 구분 <select value={kind} onChange={(e) => setKind(e.target.value as Summary["validation_kind"])}><option value="USER_OBSERVATION">사용자 참여 관찰</option><option value="SYNTHETIC">Synthetic 검증</option></select></label>
      {store ? <SummaryData store={store} kind={kind} load={load} /> : <p>조회 가능한 매장이 없습니다.</p>}</>}
  </article>;
}
