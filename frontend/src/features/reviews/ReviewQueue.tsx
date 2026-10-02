import { useState } from "react";
import { Check, FilePenLine, FileSearch, X } from "lucide-react";
import { mockApi } from "../../api/mockApi";
import type { ReviewAction, ReviewDetail } from "../../contracts/types";
import { Button, PageHeading, PreviewNotice, StateMessage } from "../../components/ui";
import { ageLabel, dateTime } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";
import { Badge } from "../../components/IncidentBadge";

const actions = [
  { key: "approve", label: "승인", icon: Check },
  { key: "edit", label: "수정 요청", icon: FilePenLine },
  { key: "reject", label: "반려", icon: X },
  { key: "request_more_evidence", label: "추가 증거 요청", icon: FileSearch },
] as const;

const statusLabels = { PENDING: "검토 대기", APPROVED: "승인됨", REJECTED: "반려됨" };
const evidenceLabels = { AVAILABLE: "확인 가능", PENDING: "수집 대기", REJECTED: "제외됨" };
const reviewType = (value: string) => value === "Corrective Action" ? "시정·예방 조치 검토" : value;
const actorLabel = (value: string) => value === "CAPA Agent" ? "조치안 작성 담당" : value;
const sourceLabel = (value: string) => ({ temperature_sensor: "온도 센서", telemetry: "센서 측정 기록" } as Record<string, string>)[value] ?? value;

async function loadReviews() {
  const approvals = await mockApi.listApprovals();
  const details = await Promise.all(approvals.map((item) => mockApi.getReviewDetail(item.id)));
  return approvals.map((approval, index) => ({ approval, detail: details[index] }));
}

function EvidencePanel({ detail }: { detail: ReviewDetail }) {
  return <section className="panel">
    <h2>판단에 사용한 증거</h2>
    {detail.evidence.length === 0 ? <p>추가 증거가 등록되면 이곳에서 확인할 수 있습니다.</p> :
      <div className="space-y-3">{detail.evidence.map((evidence) => <article key={evidence.id} className="rounded-lg border border-slate-200 p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <strong className="text-sm text-slate-700">{sourceLabel(evidence.source)}</strong>
          <span className="tag status">{evidenceLabels[evidence.status]}</span>
          <span className="text-xs text-slate-500">신뢰도 {Math.round(evidence.confidence * 100)}%</span>
        </div>
        <p>{evidence.summary}</p>
        <small className="text-slate-500">{sourceLabel(evidence.type)} · 증거 ID {evidence.id}</small>
      </article>)}</div>}
  </section>;
}

export function ReviewQueue() {
  const query = useQuery(loadReviews);
  const [selectedId, setSelectedId] = useState<string>();
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState<ReviewAction>();
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; message: string }>();
  const items = query.data ?? [];
  const selected = items.find((item) => item.approval.id === selectedId);

  function selectReview(id: string) {
    setSelectedId(id);
    setNote("");
    setFeedback(undefined);
  }

  async function submitAction(action: ReviewAction) {
    if (!selected) return;
    setSubmitting(action);
    setFeedback(undefined);
    try {
      await mockApi.reviewAction(selected.approval.id, action, note);
      const label = actions.find((item) => item.key === action)?.label ?? "검토";
      setFeedback({ kind: "success", message: `${label} 결과를 기록했습니다. 검토 이력에서 확인할 수 있습니다.` });
      setNote("");
      query.reload();
    } catch (error) {
      setFeedback({ kind: "error", message: error instanceof Error ? error.message : "검토 결과를 저장하지 못했습니다. 다시 시도해 주세요." });
    } finally {
      setSubmitting(undefined);
    }
  }

  return <section className="page">
    <PageHeading title="검토 대기함" description="제안된 조치와 근거를 확인하고, 허용된 검토 결정을 기록하세요.">
      <span className="tag high">검토 대기 {items.filter(({ approval }) => approval.status === "PENDING").length}건</span>
    </PageHeading>
    <PreviewNotice />
    {query.loading && !query.data ? <StateMessage kind="loading" title="검토 요청을 불러오는 중입니다" /> :
      query.error ? <StateMessage kind="error" title="검토 요청을 불러오지 못했습니다" onRetry={query.reload}>잠시 후 다시 불러와 주세요.</StateMessage> :
      items.length === 0 ? <StateMessage title="등록된 검토 요청이 없습니다">검토가 필요한 조치안이 도착하면 목록에 표시됩니다.</StateMessage> : <>
        <div className="table-wrap mb-5 overflow-x-auto">
          <table>
            <thead><tr><th>인시던트</th><th>검토 유형</th><th>위험도</th><th>요청자</th><th>요청 시각</th><th>경과 시간</th><th>증거 충족도</th><th>상태</th></tr></thead>
            <tbody>{items.map(({ approval, detail }) => <tr key={approval.id} className={selectedId === approval.id ? "bg-blue-50/60" : ""}>
              <td><button className="text-left text-blue-700 hover:underline disabled:opacity-50" disabled={!!submitting} onClick={() => selectReview(approval.id)} aria-pressed={selectedId === approval.id}>
                <span className="block text-xs text-slate-500">{detail?.incident_display_id ?? approval.incident_id}</span>
                <strong>{detail?.incident_title ?? "인시던트 검토 상세"}</strong>
              </button></td>
              <td>{reviewType(approval.type)}</td><td><Badge value={approval.risk_level} /></td>
              <td>{actorLabel(approval.requester)}</td><td>{dateTime(approval.requested_at)}</td>
              <td>{ageLabel(approval.requested_at, mockApi.asOf)}</td><td>{approval.evidence_completeness}%</td>
              <td><span className="tag status">{statusLabels[approval.status]}</span></td>
            </tr>)}</tbody>
          </table>
        </div>
        {!selected ? <StateMessage title="검토할 항목을 선택해 주세요">인시던트 제목을 누르면 조치안, 증거, 검토 권한을 확인할 수 있습니다.</StateMessage> :
          !selected.detail ? <StateMessage kind="error" title="이 검토의 상세 자료를 찾을 수 없습니다" onRetry={query.reload}>목록을 다시 불러오거나 다른 항목을 선택해 주세요.</StateMessage> : <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-4">
              <section className="panel">
                <h2>{selected.detail.incident_title}</h2>
                <p>{selected.detail.incident_display_id} · 검토 기한 {dateTime(selected.detail.due_at)}</p>
                <dl className="grid gap-3 text-sm">
                  <div><dt className="mb-1 font-semibold text-slate-700">제안된 조치</dt><dd className="text-slate-600">{selected.detail.proposed_action}</dd></div>
                  <div><dt className="mb-1 font-semibold text-slate-700">기대 효과</dt><dd className="text-slate-600">{selected.detail.expected_effect}</dd></div>
                  <div><dt className="mb-1 font-semibold text-slate-700">검증 기준</dt><dd className="text-slate-600">{selected.detail.verification_criteria}</dd></div>
                </dl>
              </section>
              <EvidencePanel detail={selected.detail} />
              <section className="panel">
                <h2>검토 이력</h2>
                {selected.detail.history.length === 0 ? <p>아직 기록된 검토 결정이 없습니다.</p> : <ol className="space-y-3">
                  {selected.detail.history.map((event, index) => <li key={`${event.occurred_at}-${index}`} className="border-l-2 border-blue-100 pl-3 text-sm">
                    <p>{event.summary}</p><small className="text-slate-500">{actorLabel(event.actor)} · {dateTime(event.occurred_at)}</small>
                  </li>)}
                </ol>}
              </section>
            </div>
            <aside className="review-panel h-fit">
              <h2>검토 결정</h2>
              <p>버튼 아래의 권한 안내와 증거를 확인한 뒤 선택하세요.</p>
              <label htmlFor="review-note" className="mb-2 block text-sm font-semibold text-slate-700">결정 사유 또는 요청 내용</label>
              <textarea id="review-note" rows={4} value={note} disabled={!!submitting} onChange={(event) => setNote(event.target.value)} className="w-full rounded-lg border border-slate-300 p-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="수정할 내용, 반려 사유 또는 필요한 증거를 적어 주세요." aria-describedby="review-note-help" />
              <p id="review-note-help" className="mt-2">수정 요청·반려·추가 증거 요청에는 내용을 반드시 남겨 주세요. 승인에도 메모를 남길 수 있습니다.</p>
              <div className="space-y-3">{actions.map(({ key, label, icon: Icon }) => {
                const permission = selected.approval.actions[key];
                return <div key={key}>
                  <Button variant={key === "approve" ? "primary" : key === "reject" ? "danger" : "secondary"} className="w-full justify-center" disabled={!permission.allowed || !!submitting || query.loading} onClick={() => { void submitAction(key); }} aria-describedby={`review-permission-${key}`}>
                    <Icon size={15} />{submitting === key ? "결과를 기록하는 중…" : label}
                  </Button>
                  <p id={`review-permission-${key}`} className="mt-1 text-xs">{permission.reason}</p>
                </div>;
              })}</div>
              {feedback && <div className={`mt-4 rounded-lg p-3 text-sm ${feedback.kind === "error" ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-800"}`} role={feedback.kind === "error" ? "alert" : "status"}>{feedback.message}</div>}
            </aside>
          </div>}
      </>}
  </section>;
}
