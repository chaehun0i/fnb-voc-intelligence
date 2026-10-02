import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { CheckCircle2, History, RotateCcw, Save, Settings2, ShieldCheck } from "lucide-react";
import { mockApi } from "../../api/mockApi";
import type { ConfigWorkspace, ControlPlaneConfig, Severity } from "../../contracts/types";
import { Button, PageHeading, PreviewNotice, StateMessage } from "../../components/ui";
import { dateTime, severityLabels } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";

type EditableKey = { [Key in keyof ControlPlaneConfig]: ControlPlaneConfig[Key] extends boolean | number ? Key : never }[keyof ControlPlaneConfig];
type SettingField = { key: EditableKey; label: string; description: string };

const groups: Array<{ title: string; description: string; fields: SettingField[] }> = [
  { title: "실행 범위와 안전 한도", description: "한 번의 실행에서 사용하는 시간, 도구, 비용의 상한입니다.", fields: [
    { key: "max_agent_iterations", label: "최대 에이전트 반복 횟수", description: "판단과 재검토를 반복할 수 있는 횟수" },
    { key: "max_tool_calls", label: "최대 도구 호출 횟수", description: "한 실행에서 허용할 도구 호출 수" },
    { key: "parallelism", label: "병렬 처리 수", description: "동시에 진행하는 조사 작업 수" },
    { key: "timeout_seconds", label: "전체 처리 제한 시간(초)", description: "한 실행의 최대 소요 시간" },
    { key: "token_budget", label: "토큰 예산", description: "한 실행에서 사용할 수 있는 총 토큰 수" },
    { key: "cost_budget_usd", label: "비용 예산(USD)", description: "한 실행에서 허용할 예상 비용" },
  ] },
  { title: "Gemini 요청 한도", description: "공통 LLM Gateway가 사용할 기본 제공자의 요청 제한입니다.", fields: [
    { key: "gemini_concurrency", label: "Gemini 동시 요청 수", description: "동시에 전송할 요청 수" },
    { key: "gemini_rate_limit", label: "Gemini 분당 요청 수", description: "분당 허용할 최대 요청 수" },
    { key: "gemini_timeout_seconds", label: "Gemini 요청 제한 시간(초)", description: "개별 요청의 응답 대기 시간" },
  ] },
  { title: "자동화 범위", description: "자동으로 작성하거나 실행할 단계의 운영 정책입니다.", fields: [
    { key: "jev_enabled", label: "Jev 판단 엔진 사용", description: "조사 흐름을 선택하는 판단 단계" },
    { key: "auto_investigation", label: "자동 조사", description: "인시던트의 근거 자료 조사" },
    { key: "auto_rca_draft", label: "자동 원인 분석 초안", description: "수집한 증거를 바탕으로 원인 후보 작성" },
    { key: "auto_capa_draft", label: "자동 시정·예방 조치 초안", description: "원인 분석에 대한 조치안 작성" },
    { key: "auto_execute", label: "자동 조치 실행", description: "승인 정책을 충족한 조치의 실행 범위" },
  ] },
  { title: "작업 대기열 정책", description: "테넌트별 처리 자원과 재시도 한도입니다.", fields: [
    { key: "tenant_queue_concurrency", label: "테넌트별 동시 작업 수", description: "각 운영 조직에 할당할 동시 처리 수" },
    { key: "retry_limit", label: "최대 재시도 횟수", description: "실패한 작업의 재시도 상한" },
  ] },
];

const fieldsByKey = Object.fromEntries(groups.flatMap((group) => group.fields.map((field) => [field.key, field.label]))) as Record<string, string>;
const risks: Severity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

function copyConfig(config: ControlPlaneConfig): ControlPlaneConfig {
  return { ...config, approval_policy_by_risk: { ...config.approval_policy_by_risk } };
}

function numericInputs(config: ControlPlaneConfig) {
  return Object.fromEntries(groups.flatMap((group) => group.fields.filter((field) => typeof config[field.key] === "number").map((field) => [field.key, String(config[field.key])])));
}

function changeLabel(field: string) {
  if (field.startsWith("approval_policy_by_risk.")) {
    const risk = field.split(".")[1] as Severity;
    return `${severityLabels[risk] ?? risk} 위험도 사람 승인`;
  }
  return fieldsByKey[field] ?? ({ default_llm_provider: "기본 LLM 제공자", fallback_llm_provider: "대체 LLM 제공자", approval_policy_by_risk: "위험도별 사람 승인 정책" } as Record<string, string>)[field] ?? field;
}

function changeValue(value: string, field: string) {
  let parsed: unknown = value;
  try { parsed = JSON.parse(value); } catch { /* 기존 이력의 일반 문자열도 표시합니다. */ }
  if (field === "approval_policy_by_risk" && parsed && typeof parsed === "object") {
    const policy = parsed as Record<Severity, boolean>;
    return risks.map((risk) => `${severityLabels[risk]}: ${policy[risk] ? "승인 필요" : "승인 불필요"}`).join(" · ");
  }
  if (typeof parsed === "number") return parsed.toLocaleString("ko-KR");
  const text = String(parsed);
  return ({ true: "사용", false: "사용 안 함", gemini: "Gemini", ollama: "Ollama" } as Record<string, string>)[text] ?? text;
}

export function ControlPlaneSettings() {
  const query = useQuery(mockApi.getConfigWorkspace);
  const [workspace, setWorkspace] = useState<ConfigWorkspace>();
  const [draft, setDraft] = useState<ControlPlaneConfig>();
  const [numbers, setNumbers] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [rollbackReason, setRollbackReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; message: string }>();

  useEffect(() => {
    if (query.data) {
      setWorkspace(query.data);
      setDraft(copyConfig(query.data.config));
      setNumbers(numericInputs(query.data.config));
    }
  }, [query.data]);

  function applyWorkspace(next: ConfigWorkspace) {
    setWorkspace(next);
    setDraft(copyConfig(next.config));
    setNumbers(numericInputs(next.config));
    setReason("");
  }

  function cancelDraft() {
    if (!workspace) return;
    setDraft(copyConfig(workspace.config));
    setNumbers(numericInputs(workspace.config));
    setReason("");
    setFeedback(undefined);
  }

  async function saveDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft) return;
    setBusy(true);
    setFeedback(undefined);
    try {
      const parsedNumbers = Object.fromEntries(Object.entries(numbers).map(([key, value]) => [key, Number(value)]));
      const next = await mockApi.saveConfig({ ...draft, ...parsedNumbers }, reason);
      applyWorkspace(next);
      setFeedback({ kind: "success", message: `설정을 저장했습니다. 현재 버전은 ${next.config.version}입니다.` });
    } catch (error) {
      setFeedback({ kind: "error", message: error instanceof Error ? error.message : "설정을 저장하지 못했습니다. 다시 시도해 주세요." });
    } finally {
      setBusy(false);
    }
  }

  async function rollback(version: number) {
    setBusy(true);
    setFeedback(undefined);
    try {
      const next = await mockApi.rollbackConfig(version, rollbackReason);
      applyWorkspace(next);
      setRollbackReason("");
      setFeedback({ kind: "success", message: `버전 ${version}의 설정을 복원하고 새 버전 ${next.config.version}으로 기록했습니다.` });
    } catch (error) {
      setFeedback({ kind: "error", message: error instanceof Error ? error.message : "이전 설정을 복원하지 못했습니다. 다시 시도해 주세요." });
    } finally {
      setBusy(false);
    }
  }

  const dirty = !!draft && !!workspace && (
    JSON.stringify(draft) !== JSON.stringify(workspace.config) ||
    Object.entries(numbers).some(([key, value]) => value !== String(workspace.config[key as keyof ControlPlaneConfig]))
  );

  return <section className="page">
    <PageHeading title="운영 설정" description="실행 한도와 승인 정책을 조정하고, 변경 이유와 버전을 함께 관리하세요.">
      {workspace && <span className="tag status">현재 버전 {workspace.config.version}</span>}
    </PageHeading>
    <PreviewNotice />
    {query.loading && !workspace ? <StateMessage kind="loading" title="운영 설정을 불러오는 중입니다" /> :
      query.error ? <StateMessage kind="error" title="운영 설정을 불러오지 못했습니다" onRetry={query.reload}>잠시 후 다시 불러와 주세요.</StateMessage> :
      !workspace || !draft ? <StateMessage title="등록된 운영 설정이 없습니다" /> : <>
        <section className="panel mb-4">
          <h2><Settings2 size={17} /> 제공자와 적용 범위</h2>
          <p><strong>기본 제공자: Gemini</strong> · 대체 제공자: Ollama</p>
          <p>Ollama는 로컬 개발 및 대체 경로로 유지합니다. 제공자 연결과 실제 실행은 이후 공통 LLM Gateway를 통해 추가합니다.</p>
          <p>적용 범위: {workspace.scope}</p>
        </section>
        {feedback && <div className={`mb-4 rounded-lg p-4 text-sm ${feedback.kind === "error" ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-800"}`} role={feedback.kind === "error" ? "alert" : "status"}>{feedback.message}</div>}
        <form onSubmit={(event) => { void saveDraft(event); }} className="space-y-4">
          {groups.map((group) => <section className="panel" key={group.title}>
            <h2>{group.title}</h2><p>{group.description}</p>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{group.fields.map((field) => {
              const value = draft[field.key];
              const rule = workspace.rules[field.key];
              const inputId = `config-${field.key}`;
              return <div key={field.key} className="rounded-lg border border-slate-200 bg-slate-50/40 p-3">
                <label htmlFor={inputId} className="flex items-center justify-between gap-3 text-sm font-semibold text-slate-700">
                  <span>{field.label}</span>
                  {typeof value === "boolean" ? <input id={inputId} type="checkbox" className="h-4 w-4 accent-blue-600" checked={value} disabled={busy} onChange={(event) => setDraft({ ...draft, [field.key]: event.target.checked })} /> :
                    <input id={inputId} type="number" className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1.5 font-normal" required value={numbers[field.key] ?? ""} min={rule?.min} max={rule?.max} step={rule?.integer ? 1 : "any"} disabled={busy} onChange={(event) => setNumbers({ ...numbers, [field.key]: event.target.value })} aria-describedby={`${inputId}-help`} />}
                </label>
                <p id={`${inputId}-help`} className="mt-2 text-xs">{field.description}{rule && <span className="mt-1 block">허용 범위: {rule.min.toLocaleString()} ~ {rule.max.toLocaleString()}{rule.integer ? " · 정수" : ""}</span>}</p>
              </div>;
            })}</div>
          </section>)}
          <section className="panel">
            <h2><CheckCircle2 size={17} /> 위험도별 사람 승인</h2>
            <p>각 위험도에서 사람의 승인을 요청할지 설정합니다. 변경 내용은 다른 설정과 함께 저장됩니다.</p>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{risks.map((risk) => <label className="setting" key={risk}>
              {severityLabels[risk]} 위험도 승인 필요
              <input type="checkbox" className="h-4 w-4 accent-blue-600" checked={draft.approval_policy_by_risk[risk]} disabled={busy} onChange={(event) => setDraft({ ...draft, approval_policy_by_risk: { ...draft.approval_policy_by_risk, [risk]: event.target.checked } })} />
            </label>)}</div>
          </section>
          <section className="panel">
            <h2><Save size={17} /> 변경 내용 저장</h2>
            <p>{dirty ? "저장하지 않은 변경 내용이 있습니다." : "현재 저장된 설정과 동일합니다."}</p>
            <label htmlFor="config-save-reason" className="mb-2 block text-sm font-semibold text-slate-700">변경 이유</label>
            <textarea id="config-save-reason" className="w-full rounded-lg border border-slate-300 p-3 text-sm" rows={2} value={reason} required disabled={busy} onChange={(event) => setReason(event.target.value)} placeholder="이 설정을 변경하는 운영상의 이유를 남겨 주세요." />
            <p className="mt-2">{workspace.save_permission.reason}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button type="submit" variant="primary" disabled={!workspace.save_permission.allowed || busy || !dirty}><Save size={15} />{busy ? "설정 반영 중…" : "변경 내용 저장"}</Button>
              <Button type="button" disabled={busy || !dirty} onClick={cancelDraft}>변경 취소</Button>
            </div>
          </section>
        </form>
        <section className="panel mt-4">
          <h2><ShieldCheck size={17} /> 도구와 검증 범위</h2>
          <p>허용 도구 목록과 검증 기간은 운영 정책에서 제공하며 여기에서는 확인만 할 수 있습니다.</p>
          <div className="mb-3 flex flex-wrap gap-2">{workspace.allowed_tools.length ? workspace.allowed_tools.map((tool) => <span key={tool} className="tag status">{tool}</span>) : <span className="text-sm text-slate-500">등록된 허용 도구가 없습니다.</span>}</div>
          <p>검증 기간: 조치 이후 {workspace.verification_window_hours}시간</p>
        </section>
        <section className="panel mt-4">
          <h2><History size={17} /> 설정 버전과 변경 이력</h2>
          <p>이전 버전을 복원하면 새 버전으로 기록됩니다. 저장하지 않은 입력은 복원한 설정으로 바뀝니다.</p>
          <label htmlFor="config-rollback-reason" className="mb-2 block text-sm font-semibold text-slate-700">이전 설정을 복원하는 이유</label>
          <textarea id="config-rollback-reason" rows={2} value={rollbackReason} disabled={busy} onChange={(event) => setRollbackReason(event.target.value)} className="mb-2 w-full rounded-lg border border-slate-300 p-3 text-sm" placeholder="문제 상황과 복원이 필요한 이유를 남겨 주세요." />
          <p>{workspace.rollback_permission.reason}</p>
          {workspace.revisions.length === 0 ? <p>저장하면 첫 번째 변경 이력이 기록됩니다.</p> : <div className="space-y-3">
            {[...workspace.revisions].sort((a, b) => b.version - a.version).map((revision) => <details className="rounded-lg border border-slate-200 p-3" key={revision.version} open={revision.version === workspace.config.version}>
              <summary className="cursor-pointer text-sm font-semibold text-slate-700">버전 {revision.version} · {dateTime(revision.created_at)} · {revision.actor}{revision.version === workspace.config.version ? " · 현재 적용 중" : ""}</summary>
              <p className="mt-3">변경 이유: {revision.reason}</p>
              {revision.changes.length === 0 ? <p>초기 운영 설정입니다.</p> : <div className="overflow-x-auto"><table>
                <thead><tr><th>설정</th><th>이전 값</th><th>변경된 값</th></tr></thead>
                <tbody>{revision.changes.map((change) => <tr key={change.field}><td>{changeLabel(change.field)}</td><td>{changeValue(change.before, change.field)}</td><td>{changeValue(change.after, change.field)}</td></tr>)}</tbody>
              </table></div>}
              {revision.version !== workspace.config.version && <Button type="button" className="mt-3" disabled={!workspace.rollback_permission.allowed || busy} onClick={() => { void rollback(revision.version); }}><RotateCcw size={15} />버전 {revision.version}로 복원</Button>}
            </details>)}
          </div>}
        </section>
      </>}
  </section>;
}
