import { useMemo, useState } from "react";
import { decisionApi } from "../ai/decisionApi";
import { apiMode } from "../../shared/api";
import { Button, StateMessage } from "../../components/ui";
import { dateTime, severityLabels } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";

const routes: Record<string, string> = { COLD_CHAIN_INVESTIGATION: "온도·콜드체인 조사", SUPPLIER_LOT_INVESTIGATION: "공급사·로트 조사", HISTORY_RECURRENCE: "재발 이력 조사", TRANSACTION_INVESTIGATION: "거래 내역 조사", GENERAL_INVESTIGATION: "일반 조사", MANUAL_REVIEW: "사람 검토" };
const agents: Record<string, string> = { TEMPERATURE: "온도", INVENTORY: "재고", LOT: "로트", SUPPLIER: "공급사", HISTORY: "이력", TRANSACTION: "거래" };
const reasons: Record<string, string> = { ENGINE_FAILURE: "판단 처리 실패 · 자동화 중단", CRITICAL_MANUAL_GATE: "긴급 위험은 사람 검토로 제한", CATEGORY_BLOCKED: "자동 조사가 금지된 분류", AUTOMATION_DISABLED: "조직 자동화 정책이 꺼져 있음", MANUAL_REQUESTED: "사람 검토 모드 요청", STATUS_NOT_INVESTIGABLE: "현재 상태는 자동 조사 대상이 아님", FOOD_SAFETY_RISK: "식품 안전 위험을 보수적으로 반영", RECURRENCE_RISK: "재발 위험 반영", EVIDENCE_GAP: "필수 근거 정보 부족", UNKNOWN_CATEGORY: "분류 미확정 · 안전한 기본 경로", NO_ALLOWED_AGENTS: "허용된 조사 후보 없음", DATA_UNAVAILABLE: "조사에 필요한 데이터 없음", PARALLELISM_LIMIT: "병렬 처리 한도로 후보 제한", PROVIDER_POLICY_DENIED: "외부 AI 사용 정책이 허용되지 않음", HUMAN_REVIEW_REQUIRED: "사람 검토 필요" };
export function ShadowDecisionPanel({ incidentId }: { incidentId: string }) {
  const [offset, setOffset] = useState(0);
  const loader = useMemo(() => () => decisionApi.history(incidentId, 5, offset), [incidentId, offset]);
  const query = useQuery(loader);
  return <section aria-label="Jev Shadow 판단" className="mb-5 rounded-xl border border-blue-200 bg-blue-50/30 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2>Jev 결정 레이어 <span className="tag status">Shadow Decision</span></h2><Button onClick={query.reload}>판단 기록 새로고침</Button></div>
    <p>현재 Jev 판단은 실행 경로를 변경하지 않습니다. Agent/LLM 자동 실행은 아직 연결되지 않았습니다.</p>
    {apiMode === "mock" && <p className="preview-notice">예시 모드입니다. 실제 Job의 판단 기록은 HTTP 모드에서 조회합니다.</p>}
    {query.loading ? <StateMessage kind="loading" title="판단 기록을 불러오는 중입니다" /> : query.error ? <StateMessage kind="error" title="판단 기록을 불러오지 못했습니다" onRetry={query.reload}>{query.error}</StateMessage> : !query.data?.decisions.length ? <StateMessage title="아직 Shadow 판단 기록이 없습니다">Jev 사용 설정 이후 처리한 Incident 작업에서 기록이 생성됩니다. 예시 데이터를 실제 기록으로 대체하지 않습니다.</StateMessage> : <>
      {query.data.decisions.map((decision) => <article key={decision.decision_id} className="record-details">
        <strong>{routes[decision.route]} · {severityLabels[decision.risk_level]} 위험 · {decision.priority}</strong>
        {decision.error_code && <p role="alert">판단을 완료하지 못해 안전한 사람 검토 경로를 기록했습니다. 오류 코드: {decision.error_code}</p>}
        <p>사람 검토: {decision.requires_human_review ? "필요" : "불필요"} · LLM: {decision.requires_llm ? "향후 호출 필요 후보" : "필요 없음"}</p>
        <p>조사 후보(미실행): {decision.investigation_agents.map((value) => agents[value]).join(", ") || "없음"}</p>
        <ul className="list-disc pl-5">{decision.reason_codes.map((value) => <li key={value}>{reasons[value] ?? "서버가 제공한 추가 판단 근거"} <small className="muted">({value})</small></li>)}</ul>
        <p>설정 버전 {decision.config_version === 0 ? "0 · 기본 정책" : decision.config_version} · 규칙 버전 {decision.ruleset_version} · Incident 버전 {decision.incident_version}</p>
        <p>판단 시각: {dateTime(decision.decided_at)} · 처리 시간 {decision.duration_ms.toFixed(1)}ms</p>
        <small className="muted break-all">판단 ID: {decision.decision_id} · 원본 작업: {decision.source_job_id}</small>
        <p>Workflow 프로필: {decision.workflow_profile} · 예산 프로필: {decision.budget_profile}</p>
      </article>)}
      <div className="flex gap-2"><Button disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - 5))}>이전 기록</Button><Button disabled={!query.data.has_more} onClick={() => setOffset((value) => value + 5)}>다음 기록</Button></div>
    </>}
  </section>;
}
