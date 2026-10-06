import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { CheckCircle2, History, RotateCcw, Save, Settings2, ShieldCheck } from "lucide-react";
import { settingsApi, SettingsApiError } from "./api";
import { apiMode, commandKey } from "../../shared/api";
import type { RuntimeConfig, RuntimeHistory, RuntimeWorkspace } from "./types";
import type { Severity } from "../../contracts/types";
import { SelectField } from "../../components/SelectField";
import { Button, PageHeading, PreviewNotice, StateMessage } from "../../components/ui";
import { dateTime, severityLabels } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";

type EditableKey = { [Key in keyof RuntimeConfig]-?: RuntimeConfig[Key] extends boolean | number ? Key : never }[keyof RuntimeConfig];
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
    { key: "provider_concurrency", label: "Gateway 동시 요청 수", description: "제공자와 독립적인 향후 Gateway 요청 상한" },
    { key: "provider_timeout_seconds", label: "Gateway 요청 제한 시간(초)", description: "제공자와 독립적인 향후 Gateway 응답 대기 상한" },
    { key: "gemini_concurrency", label: "Gemini 동시 요청 수", description: "동시에 전송할 요청 수" },
    { key: "gemini_rate_limit", label: "Gemini 분당 요청 수", description: "분당 허용할 최대 요청 수" },
    { key: "gemini_timeout_seconds", label: "Gemini 요청 제한 시간(초)", description: "개별 요청의 응답 대기 시간" },
    { key: "structured_output_retry", label: "구조화 응답 재시도 한도", description: "향후 Gateway 응답 검증 재시도 한도" },
  ] },
  { title: "자동화 범위", description: "자동으로 작성하거나 실행할 단계의 운영 정책입니다.", fields: [
    { key: "jev_enabled", label: "Jev 판단 엔진 사용", description: "실제 Job에서 Shadow 판단만 기록하며 실행 경로를 변경하지 않습니다." },
    { key: "critical_manual_only", label: "긴급 위험 사람 검토 제한", description: "긴급 위험에서는 자동 조사 후보를 선택하지 않습니다." },
    { key: "hosted_ai_allowed", label: "향후 외부 AI 사용 허용", description: "판단 계약에만 반영합니다. 실제 LLM 전송은 아직 없습니다." },
    { key: "auto_investigation", label: "자동 조사", description: "인시던트의 근거 자료 조사" },
    { key: "auto_rca_draft", label: "자동 원인 분석 초안", description: "수집한 증거를 바탕으로 원인 후보 작성" },
    { key: "auto_capa_draft", label: "자동 시정·예방 조치 초안", description: "원인 분석에 대한 조치안 작성" },
    { key: "auto_execute", label: "자동 조치 실행", description: "승인 정책을 충족한 조치의 실행 범위" },
  ] },
  { title: "작업 대기열 정책", description: "테넌트별 처리 자원과 재시도 한도입니다.", fields: [
    { key: "tenant_queue_concurrency", label: "테넌트별 동시 작업 수", description: "각 운영 조직에 할당할 동시 처리 수" },
    { key: "retry_limit", label: "최대 재시도 횟수", description: "실패한 작업의 재시도 상한" },
    { key: "backoff_seconds", label: "재시도 기본 대기 시간(초)", description: "향후 Worker 설정 스냅샷에 적용할 기본 대기 시간" },
    { key: "critical_approver_count", label: "긴급 위험 승인자 수", description: "향후 승인 정책 적용 시 최소 승인자 수" },
    { key: "verification_window_hours", label: "조치 검증 기간(시간)", description: "향후 Workflow 검증 기간" },
  ] },
];

const fieldsByKey = Object.fromEntries(groups.flatMap((group) => group.fields.map((field) => [field.key, field.label]))) as Record<string, string>;
const risks: Severity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

function copyConfig(config: RuntimeConfig & { version: number }) {
  return structuredClone(config);
}

function numericInputs(config: RuntimeConfig) {
  return Object.fromEntries(groups.flatMap((group) => group.fields.filter((field) => typeof config[field.key] === "number").map((field) => [field.key, String(config[field.key])])));
}

function changeLabel(field: string) {
  if (field.startsWith("approval_policy_by_risk.")) {
    const risk = field.split(".")[1] as Severity;
    return `${severityLabels[risk] ?? risk} 위험도 사람 승인`;
  }
  return fieldsByKey[field] ?? ({ default_llm_provider: "기본 LLM 제공자", fallback_llm_provider: "대체 LLM 제공자", approval_policy_by_risk: "위험도별 사람 승인 정책", required_roles: "필요 승인 역할", separation_of_duties: "요청자·승인자 분리", priority_policy: "대기열 우선순위 정책", allowed_tools: "허용 도구 목록" } as Record<string, string>)[field] ?? field;
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

async function loadSettings() {
  try {
    const [workspace, history] = await Promise.all([settingsApi.current(), settingsApi.history()]);
    return { workspace, history };
  } catch (error) {
    if (error instanceof SettingsApiError && error.requestId) throw new Error(`${error.message} · 요청 ID: ${error.requestId}`, { cause: error });
    throw error;
  }
}

export function ControlPlaneSettings() {
  const query = useQuery(loadSettings);
  const [workspace, setWorkspace] = useState<RuntimeWorkspace>();
  const [history, setHistory] = useState<RuntimeHistory>();
  const [draft, setDraft] = useState<RuntimeConfig & { version: number }>();
  const [numbers, setNumbers] = useState<Record<string, string>>({});
  const [toolsInput, setToolsInput] = useState("");
  const [rolesInput, setRolesInput] = useState("");
  const [reason, setReason] = useState("");
  const [rollbackReason, setRollbackReason] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const pending = useRef<{ signature: string; key: string } | undefined>(undefined);
  const [fieldErrors, setFieldErrors] = useState<Array<{ field: string; reason?: string }>>([]);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; message: string }>();

  useEffect(() => {
    if (query.data) {
      setWorkspace(query.data.workspace);
      setHistory(query.data.history);
      setDraft(copyConfig(query.data.workspace.config));
      setNumbers(numericInputs(query.data.workspace.config));
      setToolsInput(query.data.workspace.config.allowed_tools.join(", "));
      setRolesInput(query.data.workspace.config.required_roles.join(", "));
    }
  }, [query.data]);

  function applyWorkspace(next: RuntimeWorkspace) {
    setWorkspace(next);
    setDraft(copyConfig(next.config));
    setNumbers(numericInputs(next.config));
    setToolsInput(next.config.allowed_tools.join(", "));
    setRolesInput(next.config.required_roles.join(", "));
    setReason("");
    setFieldErrors([]);
    pending.current = undefined;
  }

  function cancelDraft() {
    if (!workspace) return;
    setDraft(copyConfig(workspace.config));
    setNumbers(numericInputs(workspace.config));
    setToolsInput(workspace.config.allowed_tools.join(", "));
    setRolesInput(workspace.config.required_roles.join(", "));
    setReason("");
    setFeedback(undefined);
    setFieldErrors([]);
    pending.current = undefined;
  }

  function keyFor(signature: string) {
    if (pending.current?.signature !== signature) pending.current = { signature, key: commandKey() };
    return pending.current.key;
  }

  function showError(error: unknown) {
    if (error instanceof SettingsApiError) {
      setFieldErrors(error.details);
      setFeedback({ kind: "error", message: `${error.message}${error.requestId ? ` · 요청 ID: ${error.requestId}` : ""}` });
    } else setFeedback({ kind: "error", message: error instanceof Error ? error.message : "요청을 처리하지 못했습니다." });
  }

  function reloadSettings() { pending.current = undefined; setFeedback(undefined); setFieldErrors([]); query.reload(); }

  async function saveDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setFeedback(undefined);
    try {
      const parsedNumbers = Object.fromEntries(Object.entries(numbers).map(([key, value]) => [key, Number(value)]));
      const listInput = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);
      const { version, ...config } = { ...draft, ...parsedNumbers, allowed_tools: listInput(toolsInput), required_roles: listInput(rolesInput) };
      const signature = JSON.stringify(["save", version, config, reason.trim()]);
      const next = await settingsApi.save(config, version, reason.trim(), keyFor(signature));
      setHistory(await settingsApi.history());
      applyWorkspace(next);
      setFeedback({ kind: "success", message: `설정을 저장했습니다. 현재 버전은 ${next.config.version}입니다.` });
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
      submitting.current = false;
    }
  }

  async function rollback(version: number) {
    if (!workspace || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setFeedback(undefined);
    try {
      const signature = JSON.stringify(["rollback", version, workspace.config.version, rollbackReason.trim()]);
      const next = await settingsApi.rollback(version, workspace.config.version, rollbackReason.trim(), keyFor(signature));
      setHistory(await settingsApi.history());
      applyWorkspace(next);
      setRollbackReason("");
      setFeedback({ kind: "success", message: `버전 ${version}의 설정을 복원하고 새 버전 ${next.config.version}으로 기록했습니다.` });
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
      submitting.current = false;
    }
  }

  const dirty = !!draft && !!workspace && (
    JSON.stringify(draft) !== JSON.stringify(workspace.config) ||
    Object.entries(numbers).some(([key, value]) => value !== String(workspace.config[key as keyof RuntimeConfig])) ||
    toolsInput !== workspace.config.allowed_tools.join(", ") || rolesInput !== workspace.config.required_roles.join(", ")
  );

  return <section className="page">
    <PageHeading title="운영 설정" description="실행 한도와 승인 정책을 조정하고, 변경 이유와 버전을 함께 관리하세요.">
      {workspace && <span className="tag status">현재 버전 {workspace.config.version}</span>}
      <Button disabled={busy} onClick={reloadSettings}>최신 설정 불러오기</Button>
    </PageHeading>
    {apiMode === "mock" ? <PreviewNotice /> : <div className="preview-notice">서버에 저장된 조직별 설정과 이력을 표시합니다. 설정 저장과 Runtime 활성화는 별개입니다.</div>}
    {query.loading ? <StateMessage kind="loading" title="운영 설정을 불러오는 중입니다" /> :
      query.error ? <StateMessage kind="error" title="운영 설정을 불러오지 못했습니다" onRetry={reloadSettings}>{query.error}</StateMessage> :
      !workspace || !draft ? <StateMessage title="등록된 운영 설정이 없습니다" /> : <>
        <section className="panel mb-4">
          <h2><Settings2 size={17} /> 제공자와 적용 범위</h2>
           <p><strong>향후 Runtime 적용 설정 · 현재 Runtime 미연결</strong></p>
           <p>LLM Gateway 호출 경계는 준비되었습니다. Jev/Agent 자동 실행은 아직 연결하지 않았습니다. 허용 제공자: {workspace.effective.llm_enabled_providers?.join(", ") || "없음(호출 비활성)"} · 모델 매핑 {workspace.effective.llm_models?.length ?? 0}개 · 정책 기반 대체 호출 {workspace.effective.llm_fallback_allowed ? "허용" : "사용 안 함"}</p>
          <p>Jev만 Shadow 판단으로 연결되었습니다. 아래 제공자·Agent 자동 실행 설정은 실제 실행 기능이 아닙니다.</p>
          <fieldset disabled={busy || !workspace.save_permission.allowed} className="flex flex-wrap gap-4">
            <SelectField label="기본 LLM 제공자" value={draft.default_llm_provider} options={[{ value: "gemini", label: "Gemini" }, { value: "ollama", label: "Ollama" }]} onValueChange={(value) => setDraft({ ...draft, default_llm_provider: value as RuntimeConfig["default_llm_provider"] })} />
            <SelectField label="대체 LLM 제공자" value={draft.fallback_llm_provider} options={[{ value: "gemini", label: "Gemini" }, { value: "ollama", label: "Ollama" }]} onValueChange={(value) => setDraft({ ...draft, fallback_llm_provider: value as RuntimeConfig["fallback_llm_provider"] })} />
          </fieldset>
          <p>Ollama는 로컬 개발 및 대체 경로로 유지합니다. 제공자 연결과 실제 실행은 이후 공통 LLM Gateway를 통해 추가합니다.</p>
          <p>적용 범위: {workspace.scope}</p>
          <p>{workspace.current.reason} · 변경자: {workspace.current.created_by ?? "아직 저장하지 않음"}{workspace.current.created_at && ` · ${dateTime(workspace.current.created_at)}`}</p>
        </section>
        {feedback && <div className={`mb-4 rounded-lg p-4 text-sm ${feedback.kind === "error" ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-800"}`} role={feedback.kind === "error" ? "alert" : "status"}>{feedback.message}</div>}
        {fieldErrors.length > 0 && <ul className="mb-4 text-sm text-rose-700" aria-label="설정 필드 오류">{fieldErrors.map((error) => <li key={error.field}>{changeLabel(error.field.replace(/^body\.config\./, ""))}: {error.reason ?? "입력 형식을 확인해 주세요."}</li>)}</ul>}
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
                  {typeof value === "boolean" ? <input id={inputId} type="checkbox" className="h-4 w-4 accent-blue-600" checked={value} disabled={busy || !workspace.save_permission.allowed} onChange={(event) => setDraft({ ...draft, [field.key]: event.target.checked })} /> :
                    <input id={inputId} type="number" className="w-24 rounded-md border border-slate-300 bg-white px-2 py-1.5 font-normal" required value={numbers[field.key] ?? ""} min={rule?.min} max={rule?.max} step={rule?.integer ? 1 : "any"} disabled={busy || !workspace.save_permission.allowed} onChange={(event) => setNumbers({ ...numbers, [field.key]: event.target.value })} aria-describedby={`${inputId}-help`} />}
                </label>
                <p id={`${inputId}-help`} className="mt-2 text-xs">{field.description}{rule && <span className="mt-1 block">허용 범위: {rule.min.toLocaleString()} ~ {rule.max.toLocaleString()}{rule.integer ? " · 정수" : ""}</span>}</p>
              </div>;
            })}</div>
          </section>)}
          <section className="panel">
            <h2>Jev 조사 후보와 금지 분류</h2>
            <p>후보 선택은 서버가 데이터 가용성과 병렬 처리 한도를 적용해 결정합니다. 후보를 허용해도 Agent를 실행하지 않습니다.</p>
            <fieldset disabled={busy || !workspace.save_permission.allowed} className="flex flex-wrap gap-4">
              <legend className="mb-2 text-sm font-semibold">허용 조사 후보</legend>
              {Object.entries({ TEMPERATURE: "온도", INVENTORY: "재고", LOT: "로트", SUPPLIER: "공급사", HISTORY: "이력", TRANSACTION: "거래" }).map(([value, label]) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.allowed_agent_types.includes(value)} onChange={(event) => setDraft({ ...draft, allowed_agent_types: event.target.checked ? [...draft.allowed_agent_types, value] : draft.allowed_agent_types.filter((item) => item !== value) })} />{label}</label>)}
            </fieldset>
            <fieldset disabled={busy || !workspace.save_permission.allowed} className="mt-3 flex flex-wrap gap-4">
              <legend className="mb-2 text-sm font-semibold">자동 조사 금지 분류</legend>
              {Object.entries({ RESTRICTED: "보호 분류(해제 불가)", COLD_CHAIN: "콜드체인", SUPPLIER_LOT: "공급사·로트", TRANSACTION: "거래", FOOD_SAFETY: "식품 안전", GENERAL: "일반", UNKNOWN: "분류 미확정" }).map(([value, label]) => <label key={value} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={value === "RESTRICTED"} checked={draft.blocked_categories.includes(value)} onChange={(event) => setDraft({ ...draft, blocked_categories: event.target.checked ? [...draft.blocked_categories, value] : draft.blocked_categories.filter((item) => item !== value) })} />{label}</label>)}
            </fieldset>
          </section>
          <section className="panel">
            <h2><CheckCircle2 size={17} /> 위험도별 사람 승인</h2>
            <p>각 위험도에서 사람의 승인을 요청할지 설정합니다. 변경 내용은 다른 설정과 함께 저장됩니다.</p>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{risks.map((risk) => <label className="setting" key={risk}>
              {severityLabels[risk]} 위험도 승인 필요
              <input type="checkbox" className="h-4 w-4 accent-blue-600" checked={draft.approval_policy_by_risk[risk]} disabled={busy || !workspace.save_permission.allowed} onChange={(event) => setDraft({ ...draft, approval_policy_by_risk: { ...draft.approval_policy_by_risk, [risk]: event.target.checked } })} />
            </label>)}</div>
            <label className="setting">요청자와 승인자 분리<input type="checkbox" checked={draft.separation_of_duties} disabled={busy || !workspace.save_permission.allowed} onChange={(event) => setDraft({ ...draft, separation_of_duties: event.target.checked })} /></label>
            <label className="mt-3 block text-sm">필요 승인 역할 (쉼표 구분)<input className="ml-2 rounded border p-2" aria-label="필요 승인 역할" value={rolesInput} disabled={busy || !workspace.save_permission.allowed} onChange={(event) => setRolesInput(event.target.value)} /></label>
            <p>높음·긴급 승인 및 요청자·승인자 분리는 서버에서 보호합니다. 이 정책의 실제 Runtime 적용은 후속 개발입니다.</p>
          </section>
          <section className="panel">
            <h2><Save size={17} /> 변경 내용 저장</h2>
            <p>{dirty ? "저장하지 않은 변경 내용이 있습니다." : "현재 저장된 설정과 동일합니다."}</p>
            <label htmlFor="config-save-reason" className="mb-2 block text-sm font-semibold text-slate-700">변경 이유</label>
            <textarea id="config-save-reason" className="w-full rounded-lg border border-slate-300 p-3 text-sm" rows={2} value={reason} required disabled={busy} onChange={(event) => setReason(event.target.value)} placeholder="이 설정을 변경하는 운영상의 이유를 남겨 주세요." />
            <p className="mt-2">{workspace.save_permission.reason}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button type="submit" variant="primary" disabled={!workspace.save_permission.allowed || busy || (!dirty && workspace.config.version !== 0)}><Save size={15} />{busy ? "설정 반영 중…" : "변경 내용 저장"}</Button>
              <Button type="button" disabled={busy || !dirty} onClick={cancelDraft}>변경 취소</Button>
            </div>
          </section>
        </form>
        <section className="panel mt-4">
          <h2><ShieldCheck size={17} /> 도구와 검증 범위</h2>
          <p>시스템 예약 읽기 도구만 저장할 수 있습니다. 실제 도구 실행은 아직 연결되지 않았습니다.</p>
          <label className="block text-sm">허용 도구 (쉼표 구분)<input aria-label="허용 도구" className="mt-2 w-full rounded border p-2" value={toolsInput} disabled={busy || !workspace.save_permission.allowed} onChange={(event) => setToolsInput(event.target.value)} /></label>
          <p>대기열 우선순위 정책: {draft.priority_policy} · Worker 동시성/재시도 설정의 실제 적용은 아직 연결되지 않았습니다.</p>
        </section>
        <section className="panel mt-4">
          <h2>서버 해석값과 안전 상한</h2><p>UI는 설정 merge를 계산하지 않습니다. 상한 초과 입력은 서버에서 거부하며 조용히 낮추지 않습니다.</p>
          <div className="overflow-x-auto"><table><thead><tr><th>설정</th><th>조직 원본</th><th>서버 해석값</th><th>출처</th><th>안전 상한</th></tr></thead><tbody>{Object.keys(workspace.effective).map((key) => <tr key={key}><td>{key === "approval_policy_by_risk" ? "위험도별 승인 해석값" : changeLabel(key)}</td><td>{changeValue(JSON.stringify(workspace.config[key as keyof RuntimeConfig]), key)}</td><td>{changeValue(JSON.stringify(workspace.effective[key as keyof RuntimeConfig]), key)}</td><td>{workspace.sources[key] === "TENANT" ? "조직 설정" : "플랫폼 기본값"}</td><td>{workspace.rules[key]?.max ?? "서버 정책 검증"}</td></tr>)}</tbody></table></div>
        </section>
        <section className="panel mt-4">
          <h2><History size={17} /> 설정 버전과 변경 이력</h2>
          <p>이전 버전을 복원하면 새 버전으로 기록됩니다. 저장하지 않은 입력은 복원한 설정으로 바뀝니다.</p>
          <label htmlFor="config-rollback-reason" className="mb-2 block text-sm font-semibold text-slate-700">이전 설정을 복원하는 이유</label>
          <textarea id="config-rollback-reason" rows={2} value={rollbackReason} disabled={busy} onChange={(event) => setRollbackReason(event.target.value)} className="mb-2 w-full rounded-lg border border-slate-300 p-3 text-sm" placeholder="문제 상황과 복원이 필요한 이유를 남겨 주세요." />
          <p>{workspace.rollback_permission.reason}</p>
          {!history?.revisions.length ? <p>저장하면 첫 번째 변경 이력이 기록됩니다.</p> : <div className="space-y-3">
            {[...history.revisions].sort((a, b) => b.version - a.version).map((revision) => <details className="rounded-lg border border-slate-200 p-3" key={revision.version} open={revision.version === workspace.config.version}>
              <summary className="cursor-pointer text-sm font-semibold text-slate-700">버전 {revision.version} · {dateTime(revision.created_at)} · {revision.actor}{revision.version === workspace.config.version ? " · 현재 적용 중" : ""}</summary>
              <p className="mt-3">변경 이유: {revision.reason}</p>
              <p>부모 버전: {revision.parent_version ?? "없음"}{revision.rollback_source && ` · 복원 원본: ${revision.rollback_source}`}</p>
              {revision.changes.length === 0 ? <p>초기 운영 설정입니다.</p> : <div className="overflow-x-auto"><table>
                <thead><tr><th>설정</th><th>이전 값</th><th>변경된 값</th></tr></thead>
                <tbody>{revision.changes.map((change) => <tr key={change.field}><td>{changeLabel(change.field)}</td><td>{changeValue(change.before, change.field)}</td><td>{changeValue(change.after, change.field)}</td></tr>)}</tbody>
              </table></div>}
              {revision.version !== workspace.config.version && <div className="my-3 rounded bg-amber-50 p-3 text-sm"><p>현재 버전 {workspace.config.version}에서 버전 {revision.version}의 값으로 복원하면 새 버전이 생성됩니다. 현재 안전 상한을 재검증하며 Runtime 실행을 되돌리는 작업은 아닙니다.</p>{revision.rollback_changes && <ul>{revision.rollback_changes.map((change) => <li key={change.field}>{changeLabel(change.field)}: {changeValue(change.before, change.field)} → {changeValue(change.after, change.field)}</li>)}</ul>}{revision.compared_to_version !== undefined && <p>서버 차이 비교 기준: 버전 {revision.compared_to_version}</p>}</div>}
              {revision.version !== workspace.config.version && <Button type="button" className="mt-3" disabled={!workspace.rollback_permission.allowed || busy} onClick={() => { void rollback(revision.version); }}><RotateCcw size={15} />버전 {revision.version}로 복원</Button>}
            </details>)}
          </div>}
          {history && <div className="mt-3 flex gap-2"><Button disabled={busy || history.offset === 0} onClick={() => { void settingsApi.history(history.limit, Math.max(0, history.offset-history.limit)).then(setHistory).catch(showError); }}>이전 이력</Button><Button disabled={busy || !history.has_more} onClick={() => { void settingsApi.history(history.limit, history.offset+history.limit).then(setHistory).catch(showError); }}>다음 이력</Button></div>}
        </section>
      </>}
  </section>;
}
