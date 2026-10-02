import { useMemo, useState } from "react";
import { Filter, Search } from "lucide-react";
import { apiMode, incidentApi } from "../../api/incidents";
import { mockApi } from "../../api/mockApi";
import { Badge } from "../../components/IncidentBadge";
import { SelectField } from "../../components/SelectField";
import { Button, PageHeading, StateMessage } from "../../components/ui";
import { CreateIncident } from "./CreateIncident";
import { ageLabel, dateTime, severityLabels, statusLabels } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";

export function IncidentList({ onSelect, refresh = 0 }: { onSelect: (id: string) => void; refresh?: number }) {
  const loader = useMemo(() => () => incidentApi.listIncidents(), [refresh]);
  const query = useQuery(loader);
  const [creating, setCreating] = useState(false);
  const items = query.data ?? [];
  const asOf = apiMode === "http" ? new Date().toISOString() : mockApi.asOf;
  const [status, setStatus] = useState("ALL"); const [severity, setSeverity] = useState("ALL"); const [store, setStore] = useState("ALL"); const [search, setSearch] = useState("");
  const filtered = items.filter((item) => (status === "ALL" || item.status === status) && (severity === "ALL" || item.severity === severity) && (store === "ALL" || item.store === store) && `${item.display_id} ${item.title} ${item.owner}`.toLowerCase().includes(search.toLowerCase()));
  return <section className="page">
    <PageHeading title="인시던트" description="운영 이슈를 검색하고 증거부터 검증까지 해결 과정을 확인하세요."><div className="flex items-center gap-3"><span className="tag status">총 {items.length}건</span>{apiMode === "http" && <Button variant="primary" onClick={() => setCreating(true)}>인시던트 등록</Button>}</div></PageHeading>
    <div className="filters"><Filter size={16} /><SelectField label="상태 필터" value={status} options={[{ value: "ALL", label: "전체 상태" }, ...Object.entries(statusLabels).map(([value, label]) => ({ value, label }))]} onValueChange={setStatus} /><SelectField label="심각도 필터" value={severity} options={[{ value: "ALL", label: "전체 심각도" }, ...Object.entries(severityLabels).map(([value, label]) => ({ value, label }))]} onValueChange={setSeverity} /><SelectField label="매장 필터" value={store} options={[{ value: "ALL", label: "전체 매장" }, ...[...new Set(items.map((item) => item.store))].map((value) => ({ value, label: value }))]} onValueChange={setStore} /><label className="search-field"><Search size={16} /><input aria-label="인시던트 검색" placeholder="제목·ID·담당자 검색" value={search} onChange={(event) => setSearch(event.target.value)} /></label></div>
    {query.loading ? <StateMessage kind="loading" title="인시던트를 불러오는 중입니다" /> : query.error ? <StateMessage kind="error" title="인시던트를 불러오지 못했습니다" onRetry={query.reload}>API 연결 설정을 확인해 주세요.</StateMessage> : filtered.length === 0 ? <StateMessage title={items.length ? "조건에 맞는 인시던트가 없습니다" : "등록된 인시던트가 없습니다"}>검색어나 필터를 확인해 주세요.</StateMessage> : <div className="table-wrap"><table><thead><tr><th>인시던트</th><th>심각도</th><th>상태</th><th>매장</th><th>담당자</th><th>발생 시각</th><th>경과 시간</th><th>SLA 기한</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><span className="muted">{item.display_id}</span><div><button className="text-link incident-title" onClick={() => onSelect(item.id)}>{item.title}</button></div></td><td><Badge value={item.severity} /></td><td><Badge value={item.status} kind="status" /></td><td>{item.store}</td><td>{item.owner}</td><td>{dateTime(item.created_at)}</td><td>{ageLabel(item.created_at, asOf)}</td><td>{dateTime(item.sla_due_at)}</td></tr>)}</tbody></table></div>}
    {creating && <CreateIncident onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); query.reload(); onSelect(id); }} />}
  </section>;
}
