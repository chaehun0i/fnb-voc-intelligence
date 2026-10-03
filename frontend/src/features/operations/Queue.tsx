import { Fragment, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronDown, ChevronUp, RefreshCw, RotateCcw, X } from "lucide-react";
import { mockApi } from "../../api/mockApi";
import { jobApi, JobApiError } from "../../api/jobs";
import { apiMode } from "../../api/incidents";
import { commandKey } from "../../api/auth";
import { SelectField } from "../../components/SelectField";
import { Button, PageHeading, PreviewNotice, StateMessage, StatCard } from "../../components/ui";
import type { QueueJob } from "../../contracts/types";
import { ageLabel, dateTime } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";

const statusLabels: Record<QueueJob["status"], string> = { QUEUED: "대기 (미리보기)", PENDING: "대기", RUNNING: "처리 중", FAILED: "실패", DLQ: "실패 보관함", COMPLETED: "완료", CANCELLED: "취소" };
const priorityLabels: Record<QueueJob["priority"], string> = { P1: "우선 처리", P2: "일반 처리", P3: "낮은 우선순위" };
const statusOptions = [{ value: "ALL", label: "모든 상태" }, ...Object.entries(statusLabels).map(([value, label]) => ({ value, label }))];
const priorityOptions = [{ value: "ALL", label: "모든 우선순위" }, ...Object.entries(priorityLabels).map(([value, label]) => ({ value, label }))];

export function Queue() {
  const { data: jobs, loading, error, reload } = useQuery(jobApi.listJobs);
  const [status, setStatus] = useState("ALL");
  const [tenant, setTenant] = useState("ALL");
  const [priority, setPriority] = useState("ALL");
  const [expandedId, setExpandedId] = useState<string>();
  const [detail, setDetail] = useState<QueueJob>();
  const [detailLoading, setDetailLoading] = useState(false);
  const detailRequest = useRef(0);
  const [pendingId, setPendingId] = useState<string>();
  const [feedback, setFeedback] = useState("");
  const [reason, setReason] = useState("");
  const busy = useRef(false);
  const attempt = useRef<{ signature: string; key: string } | undefined>(undefined);
  const tenants = Array.from(new Set(jobs?.map((job) => job.tenant_id) ?? []));
  const filtered = jobs?.filter((job) => (status === "ALL" || job.status === status) && (tenant === "ALL" || job.tenant_id === tenant) && (priority === "ALL" || job.priority === priority)) ?? [];

  function refresh() {
    detailRequest.current++;
    setExpandedId(undefined); setDetail(undefined); reload();
  }

  async function openDetail(job: QueueJob) {
    const request = ++detailRequest.current;
    setExpandedId(job.id); setDetail(undefined); setDetailLoading(true); setReason("");
    try { const value = await jobApi.getJob(job.id); if (request === detailRequest.current) setDetail(value); }
    catch (error) { if (request === detailRequest.current) setFeedback(error instanceof Error ? error.message : "상세를 불러오지 못했습니다."); }
    finally { if (request === detailRequest.current) setDetailLoading(false); }
  }

  async function act(job: QueueJob, action: "retry" | "cancel") {
    if (!job.actions[action].allowed || busy.current) return;
    if (apiMode === "http" && !reason.trim()) { setFeedback("처리 사유를 입력해 주세요."); return; }
    busy.current = true;
    const signature = JSON.stringify([job.id, action, reason.trim(), job.version]);
    if (attempt.current?.signature !== signature) attempt.current = { signature, key: commandKey() };
    setPendingId(job.id);
    setFeedback("");
    try {
      const updated = await jobApi.jobAction(job.id, action, reason, attempt.current.key, job.version);
      attempt.current = undefined;
      setExpandedId(undefined);
      setDetail(undefined);
      setFeedback(`${updated.type}: ${action === "retry" ? "재시도 요청" : "취소 요청"}이 ${apiMode === "http" ? "서버에 기록되었습니다" : "미리보기에 반영되었습니다"}.`);
      reload();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "요청을 처리하지 못했습니다. 다시 시도하세요.");
      if (error instanceof JobApiError && ["CONFLICT", "IDEMPOTENCY_CONFLICT", "JOB_TRANSITION_NOT_ALLOWED"].includes(error.code)) refresh();
    } finally {
      setPendingId(undefined);
      busy.current = false;
    }
  }

  return (
    <section className="page">
      <PageHeading title="작업 대기열" description="매장별 작업 진행, 실패 사유와 재시도 가능 여부를 확인하세요.">
        <Button onClick={refresh} disabled={loading}><RefreshCw size={15} aria-hidden="true" /> 새로고침</Button>
      </PageHeading>
      {apiMode === "http" ? <p className="preview-notice">실제 서버 작업 · 재시도와 취소는 권한 검사와 감사 기록을 거칩니다.</p> : <PreviewNotice />}
      {feedback && <p className="action-feedback" role="status">{feedback}</p>}
      {loading ? <StateMessage kind="loading" title="작업 목록을 불러오는 중입니다" /> : error ? (
        <StateMessage kind="error" title="작업 목록을 불러오지 못했습니다" onRetry={reload}>{error}</StateMessage>
      ) : !jobs?.length ? <StateMessage title="현재 실행 대기 또는 실패한 작업이 없습니다.">새 작업이 등록되면 처리 상태를 여기에서 확인할 수 있습니다.</StateMessage> : (
        <>
          <div className="summary-grid">
            <StatCard label="대기 / 처리 중" value={`${jobs.filter((job) => ["QUEUED", "PENDING", "RUNNING"].includes(job.status)).length}건`} hint="현재 처리 대상 작업" />
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
                  {filtered.map((listed) => { const job = detail?.id === listed.id ? detail : listed; return (
                    <Fragment key={job.id}>
                      <tr>
                        <td className="incident-title">{job.type}</td>
                        <td>{job.tenant_id}</td>
                        <td>{priorityLabels[job.priority]}</td>
                        <td><span className={`tag ${job.status === "FAILED" || job.status === "DLQ" ? "critical" : job.status === "COMPLETED" ? "low" : "status"}`}>{statusLabels[job.status]}</span></td>
                        <td>{ageLabel(job.queued_at, apiMode === "http" ? new Date().toISOString() : mockApi.asOf)}</td>
                        <td>{job.attempts} / {job.max_attempts}회</td>
                        <td><Button onClick={() => void openDetail(job)} aria-expanded={expandedId === job.id} aria-controls={`job-detail-${job.id}`} aria-label={`${job.type} 상세 ${expandedId === job.id ? "닫기" : "보기"}`}>{expandedId === job.id ? <ChevronUp size={15} aria-hidden="true" /> : <ChevronDown size={15} aria-hidden="true" />} 상세</Button></td>
                      </tr>
                      {expandedId === job.id && (
                        <Dialog.Root open onOpenChange={(open) => { if (!open) { detailRequest.current++; setExpandedId(undefined); } }}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content" aria-describedby="queue-detail-description">
                          <header className="dialog-header"><Dialog.Title>작업 상세</Dialog.Title><Dialog.Close className="dialog-close" aria-label="작업 상세 닫기"><X size={19} /></Dialog.Close></header>
                          <Dialog.Description id="queue-detail-description" className="sr-only">최신 실행 상태와 처리 가능 여부를 확인합니다.</Dialog.Description>
                          <div id={`job-detail-${job.id}`} className="dialog-body">
                            {feedback && <p role="status" className="action-feedback">{feedback}</p>}
                            {detailLoading ? <StateMessage kind="loading" title="작업 상세를 불러오는 중입니다" /> : !detail ? <StateMessage kind="error" title="작업 상세를 확인할 수 없습니다" onRetry={() => void openDetail(listed)} /> : <>
                            <dl className="detail-list">
                              <div><dt>작업 식별자</dt><dd><code>{job.id}</code></dd></div>
                              <div><dt>관련 인시던트</dt><dd>{job.incident_id ?? "연결된 인시던트 없음"}</dd></div>
                              <div><dt>등록 시각</dt><dd>{dateTime(job.queued_at)}</dd></div>
                              <div><dt>실행 설정 버전</dt><dd>v{job.config_version}</dd></div>
                              <div><dt>상관관계 식별자</dt><dd><code>{job.correlation_id}</code></dd></div>
                              <div><dt>원본 재시도 작업</dt><dd>{job.parent_job_id ?? "최초 실행"}</dd></div>
                              <div><dt>데이터 버전</dt><dd>{job.version ?? "미리보기"}</dd></div>
                              <div><dt>실행 가능 시각</dt><dd>{job.available_at ? dateTime(job.available_at) : "즉시"}</dd></div>
                              <div><dt>시작 / 완료</dt><dd>{job.started_at ? dateTime(job.started_at) : "미시작"} / {job.completed_at ? dateTime(job.completed_at) : "미완료"}</dd></div>
                              <div><dt>잠금 만료</dt><dd>{job.lease_until ? dateTime(job.lease_until) : "잠금 없음"}</dd></div>
                              <div><dt>오류 코드</dt><dd>{job.error_code ?? "없음"}</dd></div>
                            </dl>
                            {job.error_summary && <div className="mt-4 rounded-lg bg-rose-50 p-3 text-rose-800"><strong>실패 사유</strong><p className="mt-1 mb-0">{job.error_summary}</p></div>}
                            {job.status === "DLQ" && <p className="mt-3 text-sm muted">자동 재시도가 끝난 작업입니다. 실패 사유와 아래 처리 가능 여부를 확인하세요.</p>}
                            {apiMode === "http" && <label className="field mt-4">처리 사유<textarea aria-label="작업 처리 사유" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={2000} disabled={pendingId !== undefined} /></label>}
                            <div className="grid grid-cols-2 gap-5 mt-4">
                              <div><Button onClick={() => void act(job, "retry")} disabled={!job.actions.retry.allowed || pendingId !== undefined} aria-describedby={`retry-permission-${job.id}`}><RotateCcw size={15} aria-hidden="true" /> {pendingId === job.id ? "처리 중…" : "재시도"}</Button><p id={`retry-permission-${job.id}`} className="mt-2 text-sm muted">{job.actions.retry.reason}</p></div>
                              <div><Button variant="danger" onClick={() => void act(job, "cancel")} disabled={!job.actions.cancel.allowed || pendingId !== undefined} aria-describedby={`cancel-permission-${job.id}`}><X size={15} aria-hidden="true" /> 취소</Button><p id={`cancel-permission-${job.id}`} className="mt-2 text-sm muted">{job.actions.cancel.reason}</p></div>
                            </div>
                            </>}
                          </div>
                        </Dialog.Content></Dialog.Portal></Dialog.Root>
                      )}
                    </Fragment>
                  ); })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
