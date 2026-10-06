import { ArrowDown, Bot, RefreshCw, Wrench } from "lucide-react";
import { mockApi } from "../../api/mockApi";
import { apiMode } from "../../api/client";
import { HistoryTracePage } from "./HistoryTrace";
import { Button, PageHeading, PreviewNotice, StateMessage, StatCard } from "../../components/ui";
import type { AgentRun, AgentStep } from "../../contracts/types";
import { statusLabels as incidentStatusLabels } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";

const stepLabels: Record<string, string> = {
  "Jev Decision": "조사 필요성 판단",
  LangGraph: "조사 흐름 구성",
  "Investigation fan-out": "분야별 병렬 조사",
  "Transaction Agent": "거래 조사",
  "Inventory Agent": "재고 조사",
  "Lot Agent": "로트 조사",
  "Supplier Agent": "공급사 조사",
  "History Agent": "과거 이력 조사",
  "Evidence Aggregation": "증거 통합",
  "RCA Agent": "원인 분석",
  "CAPA Agent": "조치안 작성",
  "Human Approval": "담당자 승인",
};
const stepStatusLabels: Record<AgentStep["status"], string> = { PENDING: "대기", RUNNING: "실행 중", COMPLETED: "완료", FAILED: "실패" };
const runStatusLabels: Record<AgentRun["status"], string> = { RUNNING: "진행 중", COMPLETED: "실행 완료", FAILED: "실행 실패" };
const investigationNames = ["Transaction Agent", "Inventory Agent", "Lot Agent", "Supplier Agent", "History Agent"];

function Stage({ step }: { step: AgentStep }) {
  return <div className={`trace-stage ${step.status.toLowerCase()}`}><strong>{stepLabels[step.name] ?? step.name}</strong><span className={`tag ${step.status === "FAILED" ? "critical" : step.status === "COMPLETED" ? "low" : "status"}`}>{stepStatusLabels[step.status]}</span></div>;
}

export function AgentTrace() {
  return apiMode === "http" ? <HistoryTracePage /> : <DemoAgentTrace />;
}

function DemoAgentTrace() {
  const { data: run, loading, error, reload } = useQuery(mockApi.getAgentRun);

  if (loading) return <section className="page"><StateMessage kind="loading" title="실행 이력을 불러오는 중입니다" /></section>;
  if (error) return <section className="page"><StateMessage kind="error" title="실행 이력을 불러오지 못했습니다" onRetry={reload}>잠시 후 다시 시도하세요.</StateMessage></section>;
  if (!run?.steps.length) return <section className="page"><PageHeading title="실행 추적" description="조사와 조치의 판단 근거를 확인하세요." /><StateMessage title="확인할 실행 이력이 없습니다" /></section>;

  const parallelSteps = run.steps.filter((step) => investigationNames.includes(step.name));
  const prefix = run.steps.filter((step) => ["Jev Decision", "LangGraph", "Investigation fan-out"].includes(step.name));
  const suffix = run.steps.filter((step) => !investigationNames.includes(step.name) && !prefix.includes(step));
  const totalTokens = run.steps.reduce((sum, step) => sum + step.token_usage, 0);
  const totalCost = run.steps.reduce((sum, step) => sum + step.cost_usd, 0);

  return (
    <section className="page">
      <PageHeading title="실행 추적" description="어떤 조사와 증거를 거쳐 조치안이 만들어졌는지 단계별로 확인하세요.">
        <Button onClick={reload}><RefreshCw size={15} aria-hidden="true" /> 새로고침</Button>
      </PageHeading>
      <PreviewNotice />
      <div className="summary-grid">
        <StatCard label="현재 실행 상태" value={runStatusLabels[run.status]} />
        <StatCard label="완료한 단계" value={`${run.steps.filter((step) => step.status === "COMPLETED").length} / ${run.steps.length}`} />
        <StatCard label="사용 토큰" value={totalTokens.toLocaleString()} hint="단계별 사용량 합계" />
        <StatCard label="예상 비용" value={`$${totalCost.toFixed(3)}`} hint="단계별 비용 합계 · USD" />
      </div>
      <article className="panel">
        <h2><Bot size={17} aria-hidden="true" /> 조사와 조치 흐름</h2>
        <p>분야별 조사를 병렬로 진행한 뒤 근거를 모아 원인과 조치안을 검토합니다. 각 단계의 상세에서 판단 근거를 확인할 수 있습니다.</p>
        <div className="trace-flow" aria-label="실행 단계 흐름">
          {prefix.map((step) => <div key={step.id}><Stage step={step} /><ArrowDown className="mx-auto my-2 text-slate-400" size={18} aria-hidden="true" /></div>)}
          {parallelSteps.length > 0 && <><div className="trace-fanout">{parallelSteps.map((step) => <Stage key={step.id} step={step} />)}</div><ArrowDown className="mx-auto my-2 text-slate-400" size={18} aria-hidden="true" /></>}
          {suffix.map((step, index) => <div key={step.id}><Stage step={step} />{index < suffix.length - 1 && <ArrowDown className="mx-auto my-2 text-slate-400" size={18} aria-hidden="true" />}</div>)}
        </div>
        <details className="record-details mt-4">
          <summary>실행 식별 정보</summary>
          <dl className="detail-list mt-3">
            <div><dt>실행 식별자</dt><dd><code>{run.id}</code></dd></div>
            <div><dt>관련 인시던트</dt><dd>{run.incident_id}</dd></div>
            {run.correlation_id && <div><dt>상관관계 식별자</dt><dd><code>{run.correlation_id}</code></dd></div>}
            {run.config_version !== undefined && <div><dt>실행 설정 버전</dt><dd>v{run.config_version}</dd></div>}
          </dl>
        </details>
      </article>
      <div className="mt-5 space-y-3">
        {run.steps.map((step, index) => (
          <article className="panel !min-h-0" key={step.id}>
            <div className="flex items-center justify-between gap-3 mb-3"><h2 className="!mb-0">{index + 1}. {stepLabels[step.name] ?? step.name}</h2><span className={`tag ${step.status === "FAILED" ? "critical" : step.status === "COMPLETED" ? "low" : "status"}`}>{stepStatusLabels[step.status]}</span></div>
            <p>{step.decision_summary}</p>
            <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-500 mb-3"><span>소요 시간 {step.latency_ms.toLocaleString()}ms</span><span>재시도 {step.retry_count}회</span><span>토큰 {step.token_usage.toLocaleString()}</span><span>비용 ${step.cost_usd.toFixed(3)}</span><span>도구 호출 {step.tool_calls.length}건</span></div>
            {step.state_transition && <p>인시던트 상태: {incidentStatusLabels[step.state_transition.from]} → {incidentStatusLabels[step.state_transition.to]}</p>}
            <details className="record-details">
              <summary>기술 상세와 도구 호출 보기</summary>
              <dl className="detail-list mt-3"><div><dt>단계 식별자</dt><dd><code>{step.id}</code></dd></div><div><dt>실행 단계 이름</dt><dd><code>{step.name}</code></dd></div></dl>
              {step.tool_calls.length ? <div className="table-wrap mt-4"><table aria-label={`${stepLabels[step.name] ?? step.name} 도구 호출`}><thead><tr><th>도구 / 식별자</th><th>결과</th><th>소요 시간</th><th>결과 요약</th></tr></thead><tbody>{step.tool_calls.map((tool) => <tr key={tool.id}><td><Wrench size={14} className="inline mr-1" aria-hidden="true" /><code>{tool.name}</code><div className="muted mt-1"><code>{tool.id}</code></div></td><td><span className={`tag ${tool.status === "SUCCESS" ? "low" : "critical"}`}>{tool.status === "SUCCESS" ? "성공" : "실패"}</span></td><td>{tool.latency_ms.toLocaleString()}ms</td><td>{tool.summary}</td></tr>)}</tbody></table></div> : <p className="!mt-3">이 단계에서는 도구를 호출하지 않았습니다.</p>}
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}
