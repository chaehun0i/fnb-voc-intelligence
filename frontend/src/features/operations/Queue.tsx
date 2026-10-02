import { Fragment, useState } from "react";
import { ChevronDown, ChevronUp, RefreshCw, RotateCcw, X } from "lucide-react";
import { mockApi } from "../../api/mockApi";
import { SelectField } from "../../components/SelectField";
import { Button, PageHeading, PreviewNotice, StateMessage, StatCard } from "../../components/ui";
import type { QueueJob } from "../../contracts/types";
import { ageLabel, dateTime } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";

const statusLabels: Record<QueueJob["status"], string> = { QUEUED: "대기", RUNNING: "처리 중", FAILED: "실패", DLQ: "실패 보관함", COMPLETED: "완료", CANCELLED: "취소" };
const priorityLabels: Record<QueueJob["priority"], string> = { P1: "우선 처리", P2: "일반 처리", P3: "낮은 우선순위" };
const statusOptions = [{ value: "ALL", label: "모든 상태" }, ...Object.entries(statusLabels).map(([value, label]) => ({ value, label }))];
const priorityOptions = [{ value: "ALL", label: "모든 우선순위" }, ...Object.entries(priorityLabels).map(([value, label]) => ({ value, label }))];

export function Queue() {
  const { data: jobs, loading, error, reload } = useQuery(mockApi.listJobs);
  const [status, setStatus] = useState("ALL");
  const [tenant, setTenant] = useState("ALL");
  const [priority, setPriority] = useState("ALL");
  const [expandedId, setExpandedId] = useState<string>();
  const [pendingId, setPendingId] = useState<string>();
  const [feedback, setFeedback] = useState("");
  const tenants = Array.from(new Set(jobs?.map((job) => job.tenant_id) ?? []));
  const filtered = jobs?.filter((job) => (status === "ALL" || job.status === status) && (tenant === "ALL" || job.tenant_id === tenant) && (priority === "ALL" || job.priority === priority)) ?? [];

  async function act(job: QueueJob, action: "retry" | "cancel") {
    if (!job.actions[action].allowed) return;
    setPendingId(job.id);
    setFeedback("");
    try {
      const updated = await mockApi.jobAction(job.id, action);
      setFeedback(`${updated.type}: ${action === "retry" ? "재시도 요청" : "취소 요청"}이 미리보기에 반영되었습니다.`);
      reload();
    } catch {
      setFeedback("요청을 처리하지 못했습니다. 작업 상세를 확인한 뒤 다시 시도하세요.");
    } finally {
      setPendingId(undefined);
    }
  }

  return (
    <section className="page">
      <PageHeading title="작업 대기열" description="매장별 작업 진행, 실패 사유와 재시도 가능 여부를 확인하세요.">
        <Button onClick={reload} disabled={loading}><RefreshCw size={15} aria-hidden="true" /> 새로고침</Button>
      </PageHeading>
      <PreviewNotice />
      {feedback && <p className="action-feedback" role="status">{feedback}</p>}
      {loading ? <StateMessage kind="loading" title="작업 목록을 불러오는 중입니다" /> : error ? (
        <StateMessage kind="error" title="작업 목록을 불러오지 못했습니다" onRetry={reload}>잠시 후 다시 시도하세요.</StateMessage>
      ) : !jobs?.length ? <StateMessage title="등록된 작업이 없습니다">새 작업이 등록되면 처리 상태를 여기에서 확인할 수 있습니다.</StateMessage> : (
        <>
          <div className="summary-grid">
            <StatCard label="대기 / 처리 중" value={`${jobs.filter((job) => job.status === "QUEUED" || job.status === "RUNNING").length}건`} hint="현재 처리 대상 작업" />
            <StatCard label="실패 / 실패 보관함" value={`${jobs.filter((job) => job.status === "FAILED" || job.status === "DLQ").length}건`} hint="원인 확인이 필요한 작업" />
            <StatCard label="완료" value={`${jobs.filter((job) => job.status === "COMPLETED").length}건`} />
            <StatCard label="취소" value={`${jobs.filter((job) => job.status === "CANCELLED").length}건`} />
          </div>
          <div className="filters" aria-label="작업 필터">
            <SelectField label="작업 상태" value={status} options={statusOptions} onValueChange={setStatus} />
            <SelectField label="작업 대상" value={tenant} options={[{ value: "ALL", label: "모든 대상" }, ...tenants.map((value) => ({ value, label: value }))]} onValueChange={setTenant} />
            <SelectField label="작업 우선순위" value={priority} options={priorityOptions} onValueChange={setPriority} />
            <span className="muted text-sm">{filtered.length} / {jobs.length}건</span>
          </div>
          {!filtered.length ? <StateMessage title="조건에 맞는 작업이 없습니다">상태, 대상 또는 우선순위 필터를 변경하세요.</StateMessage> : (
            <div className="table-wrap">
              <table aria-label="작업 대기열">
                <thead><tr><th>작업</th><th>대상</th><th>우선순위</th><th>상태</th><th>등록 후 경과</th><th>시도 횟수</th><th>상세</th></tr></thead>
                <tbody>
                  {filtered.map((job) => (
                    <Fragment key={job.id}>
                      <tr>
                        <td className="incident-title">{job.type}</td>
                        <td>{job.tenant_id}</td>
                        <td>{priorityLabels[job.priority]}</td>
                        <td><span className={`tag ${job.status === "FAILED" || job.status === "DLQ" ? "critical" : job.status === "COMPLETED" ? "low" : "status"}`}>{statusLabels[job.status]}</span></td>
                        <td>{ageLabel(job.queued_at, mockApi.asOf)}</td>
                        <td>{job.attempts} / {job.max_attempts}회</td>
                        <td><Button onClick={() => setExpandedId(expandedId === job.id ? undefined : job.id)} aria-expanded={expandedId === job.id} aria-controls={`job-detail-${job.id}`} aria-label={`${job.type} 상세 ${expandedId === job.id ? "닫기" : "보기"}`}>{expandedId === job.id ? <ChevronUp size={15} aria-hidden="true" /> : <ChevronDown size={15} aria-hidden="true" />} 상세</Button></td>
                      </tr>
                      {expandedId === job.id && (
                        <tr><td colSpan={7} className="bg-slate-50">
                          <div id={`job-detail-${job.id}`} className="p-2">
                            <h3 className="text-sm font-semibold mb-3">작업 상세</h3>
                            <dl className="detail-list">
                              <div><dt>작업 식별자</dt><dd><code>{job.id}</code></dd></div>
                              <div><dt>관련 인시던트</dt><dd>{job.incident_id ?? "연결된 인시던트 없음"}</dd></div>
                              <div><dt>등록 시각</dt><dd>{dateTime(job.queued_at)}</dd></div>
                              <div><dt>실행 설정 버전</dt><dd>v{job.config_version}</dd></div>
                              <div><dt>상관관계 식별자</dt><dd><code>{job.correlation_id}</code></dd></div>
                            </dl>
                            {job.error_summary && <div className="mt-4 rounded-lg bg-rose-50 p-3 text-rose-800"><strong>실패 사유</strong><p className="mt-1 mb-0">{job.error_summary}</p></div>}
                            {job.status === "DLQ" && <p className="mt-3 text-sm muted">자동 재시도가 끝난 작업입니다. 실패 사유와 아래 처리 가능 여부를 확인하세요.</p>}
                            <div className="grid grid-cols-2 gap-5 mt-4">
                              <div><Button onClick={() => void act(job, "retry")} disabled={!job.actions.retry.allowed || pendingId !== undefined} aria-describedby={`retry-permission-${job.id}`}><RotateCcw size={15} aria-hidden="true" /> {pendingId === job.id ? "처리 중…" : "재시도"}</Button><p id={`retry-permission-${job.id}`} className="mt-2 text-sm muted">{job.actions.retry.reason}</p></div>
                              <div><Button variant="danger" onClick={() => void act(job, "cancel")} disabled={!job.actions.cancel.allowed || pendingId !== undefined} aria-describedby={`cancel-permission-${job.id}`}><X size={15} aria-hidden="true" /> 취소</Button><p id={`cancel-permission-${job.id}`} className="mt-2 text-sm muted">{job.actions.cancel.reason}</p></div>
                            </div>
                          </div>
                        </td></tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
