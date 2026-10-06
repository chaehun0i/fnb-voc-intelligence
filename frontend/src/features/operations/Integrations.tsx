import { useState } from "react";
import { Database, RefreshCw } from "lucide-react";
import { mockApi } from "../../shared/mockApi";
import { Button, PageHeading, PreviewNotice, StateMessage, StatCard } from "../../components/ui";
import type { Integration } from "../../contracts/types";
import { dateTime } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";

const labels: Record<Integration["status"], string> = { HEALTHY: "정상 연결", DEGRADED: "확인 필요", DISCONNECTED: "연결 끊김" };
const colors: Record<Integration["status"], string> = { HEALTHY: "low", DEGRADED: "high", DISCONNECTED: "critical" };

export function Integrations() {
  const { data: integrations, loading, error, reload } = useQuery(mockApi.listIntegrations);
  const [syncingId, setSyncingId] = useState<string>();
  const [feedback, setFeedback] = useState("");

  async function sync(integration: Integration) {
    if (!integration.actions.sync.allowed) return;
    setSyncingId(integration.id);
    setFeedback("");
    try {
      const result = await mockApi.syncIntegration(integration.id);
      setFeedback(`${result.name} 동기화 미리보기를 완료했습니다. 상세에서 처리 결과를 확인하세요.`);
      reload();
    } catch {
      setFeedback("동기화 결과를 불러오지 못했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setSyncingId(undefined);
    }
  }

  return (
    <section className="page">
      <PageHeading title="연동 관리" description="운영 데이터의 연결 상태, 필드 매핑과 마지막 동기화 결과를 확인하세요.">
        <Button onClick={reload} disabled={loading}><RefreshCw size={15} aria-hidden="true" /> 상태 새로고침</Button>
      </PageHeading>
      <PreviewNotice />
      {feedback && <p className="action-feedback" role="status">{feedback}</p>}
      {loading ? <StateMessage kind="loading" title="연동 상태를 불러오는 중입니다" /> : error ? (
        <StateMessage kind="error" title="연동 상태를 불러오지 못했습니다" onRetry={reload}>다시 불러온 뒤 연결 상태를 확인하세요.</StateMessage>
      ) : !integrations?.length ? <StateMessage title="등록된 연동이 없습니다">운영 데이터 연결을 등록하면 이곳에서 상태를 확인할 수 있습니다.</StateMessage> : (
        <>
          <div className="summary-grid">
            <StatCard label="전체 연동" value={`${integrations.length}개`} />
            <StatCard label="정상 연결" value={`${integrations.filter((item) => item.status === "HEALTHY").length}개`} />
            <StatCard label="확인 필요" value={`${integrations.filter((item) => item.status === "DEGRADED").length}개`} />
            <StatCard label="연결 끊김" value={`${integrations.filter((item) => item.status === "DISCONNECTED").length}개`} />
          </div>
          <div className="panels">
            {integrations.map((integration) => (
              <article className="panel" key={integration.id}>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h2 className="!mb-0"><Database size={17} aria-hidden="true" /> {integration.name}</h2>
                  <span className={`tag ${colors[integration.status]}`}>{labels[integration.status]}</span>
                </div>
                <p>{integration.description}</p>
                <p><span className="muted">분류</span> {integration.category} · <span className="muted">마지막 성공</span> {dateTime(integration.last_success_at)}</p>
                {integration.error_summary && <p className="text-rose-700">{integration.error_summary}</p>}
                <details className="record-details">
                  <summary>매핑과 동기화 상세 보기</summary>
                  <div className="pt-4">
                    <dl className="detail-list">
                      <div><dt>연결 식별자</dt><dd><code>{integration.id}</code></dd></div>
                      <div><dt>표준 데이터 모델</dt><dd><code>{integration.canonical_model}</code></dd></div>
                      <div><dt>동기화 시작</dt><dd>{dateTime(integration.sync.started_at)}</dd></div>
                      <div><dt>동기화 종료</dt><dd>{dateTime(integration.sync.ended_at)}</dd></div>
                    </dl>
                    <h3 className="text-sm font-semibold mt-5 mb-2">필드 매핑</h3>
                    <div className="table-wrap">
                      <table aria-label={`${integration.name} 필드 매핑`}>
                        <thead><tr><th>원본 필드</th><th>표준 필드</th></tr></thead>
                        <tbody>{integration.mappings.map((mapping) => <tr key={`${mapping.source}-${mapping.target}`}><td><code>{mapping.source}</code></td><td><code>{mapping.target}</code></td></tr>)}</tbody>
                      </table>
                    </div>
                    <h3 className="text-sm font-semibold mt-5 mb-2">마지막 동기화 결과</h3>
                    <dl className="detail-list">
                      <div><dt>읽은 데이터</dt><dd>{integration.sync.read_count.toLocaleString()}건</dd></div>
                      <div><dt>저장한 데이터</dt><dd>{integration.sync.written_count.toLocaleString()}건</dd></div>
                      <div><dt>건너뛴 데이터</dt><dd>{integration.sync.skipped_count.toLocaleString()}건</dd></div>
                      <div><dt>오류 데이터</dt><dd>{integration.sync.error_count.toLocaleString()}건</dd></div>
                      <div><dt>시작 위치</dt><dd><code>{integration.sync.cursor_before}</code></dd></div>
                      <div><dt>종료 위치</dt><dd><code>{integration.sync.cursor_after}</code></dd></div>
                    </dl>
                  </div>
                </details>
                <div className="mt-4">
                  <Button onClick={() => void sync(integration)} disabled={!integration.actions.sync.allowed || syncingId !== undefined} aria-describedby={`sync-permission-${integration.id}`}>
                    <RefreshCw size={15} aria-hidden="true" /> {syncingId === integration.id ? "동기화 중…" : "동기화 미리보기"}
                  </Button>
                  <p id={`sync-permission-${integration.id}`} className="!mt-2 !mb-0 muted">{integration.actions.sync.reason}</p>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
