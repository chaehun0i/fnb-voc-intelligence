"""첫 실행 상태는 서버의 매장/입력/사건 기록으로 계산합니다."""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from src.application.incidents.service import IncidentNotFound, IncidentService
from src.application.intake_schema import IntakeCommandResult, validate_tables
from src.application.ports.repositories import IncidentConflict
from src.application.security.authorization import allowed, require
from src.application.security.principal import AccessError
from src.domain.approvals.audit import AuditRecord


class DataIntake:
    def __init__(self, persistence, context, clock=None):
        self.persistence, self.context = persistence, context
        self.clock = clock or (lambda: datetime.now(UTC))

    def audit(self, uow, action, identifier):
        p, now = self.context.principal, self.clock()
        uow.audit.append(AuditRecord(str(uuid4()),
            p.tenant_id, p.principal_id, action, "data_intake", identifier, "SUCCESS",
            self.context.request_id, self.context.correlation_id, now.isoformat()))

    def status(self):
        p = self.context.principal
        require(p, "read")
        with self.persistence.transaction(p.tenant_id) as uow:
            uow.intake.expire_previews(self.clock())
            incidents = [i for i in uow.incidents.list() if allowed(p, "read", i.store)]
            stores = {s["store"] for s in uow.intake.list("STORE") if allowed(p, "read", s["store"])}
            stores.update(i.store for i in incidents)
            source_stores = [s for s in uow.intake.source_stores() if allowed(p, "read", s)]
            stores.update(source_stores)
            imports = [i for i in uow.intake.list("IMPORT") if allowed(p, "read", i["store"])]
            has_data = bool(incidents or imports or source_stores)
            config = uow.configs.current()
            analyses = [a for a in uow.intake.list("ANALYSIS") if allowed(p, "read", a["store"])]
            linked = {a["import_id"]: a["incident_id"] for a in analyses}
            runs = [run for item in incidents for run in uow.agent_runs.history(item.id, 10, 0)]
            return {"stores": sorted(stores), "has_data": has_data, "first_run": not has_data,
                "analysis_configured": bool(config and config.config.jev_enabled and config.config.auto_investigation
                    and "voc.search" in config.config.allowed_tools and "HISTORY" in config.config.allowed_agent_types),
                "can_initialize_runtime": config is None and allowed(p, "admin"),
                "checklist": {"store": bool(stores), "data": has_data, "incident": bool(incidents),
                    "investigation": bool(runs), "results": any(r.state.findings for r in runs)},
                "import_count": len(imports), "incident_count": len(incidents),
                "can_import": allowed(p, "operate"), "imports": [{**{k: i[k] for k in
                    ("import_id", "store", "sample", "row_count", "created_at")}, "incident_id": linked.get(i["import_id"])}
                    for i in sorted(imports, key=lambda i: i["created_at"], reverse=True)[:50]]}

    def add_store(self, store):
        p = self.context.principal
        require(p, "operate", store)
        if not self.context.idempotency_key:
            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
        with self.persistence.transaction(p.tenant_id) as uow:
            fingerprint = hashlib.sha256(store.encode()).hexdigest()
            cached = uow.idempotency.claim(p.principal_id, "intake_store", self.context.idempotency_key, fingerprint)
            if cached:
                return {"store": cached.store}
            existed = uow.intake.get("STORE", store)
            result = uow.intake.put("STORE", store, store, {"store": store})
            if not existed:
                self.audit(uow, "store_register", store)
            uow.idempotency.complete(p.principal_id, "intake_store", self.context.idempotency_key,
                IntakeCommandResult(kind="STORE", identifier=store, store=store))
            return result

    def preview(self, tables, store, *, kind="VOC", mappings=None):
        p, now = self.context.principal, self.clock()
        require(p, "operate", store)
        if store not in self.status()["stores"]:
            raise IncidentNotFound()
        result = validate_tables(tables, store=store, kind=kind, mappings=mappings)
        records = result.pop("records")
        identifier = str(uuid4())
        digest = hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        response = {**result, "preview_id": identifier, "digest": digest, "store": store,
            "row_count": len(records), "expires_at": (now+timedelta(minutes=15)).isoformat()}
        if result["valid"]:
            with self.persistence.transaction(p.tenant_id) as uow:
                uow.intake.lock_store(store)
                uow.intake.expire_previews(now)
                if len(uow.intake.list("PREVIEW")) >= 20:
                    raise AccessError("PREVIEW_LIMIT", 429)
                uow.intake.put("PREVIEW", identifier, store, {**response, "records": records,
                    "principal_id": p.principal_id})
        return response

    def confirm(self, identifier, digest):
        p = self.context.principal
        if not self.context.idempotency_key:
            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
        require(p, "operate")
        fingerprint = hashlib.sha256(json.dumps([identifier, digest]).encode()).hexdigest()
        with self.persistence.transaction(p.tenant_id) as uow:
            # Completed replay is available after the temporary preview has been removed.
            cached = uow.idempotency.claim(p.principal_id, "intake_confirm", self.context.idempotency_key, fingerprint)
            if cached:
                require(p, "operate", cached.store)
                return uow.intake.get("IMPORT", cached.identifier)
            draft = uow.intake.get("PREVIEW", identifier, lock=True)
            if draft is None:
                raise IncidentNotFound()
            require(p, "operate", draft["store"])
            if draft["principal_id"] != p.principal_id:
                raise AccessError()
            if datetime.fromisoformat(draft["expires_at"]) <= self.clock() or digest != draft["digest"]:
                raise IncidentConflict("미리보기를 다시 검증해 주세요.")
            receipt = self._import(uow, draft["records"], draft["store"], sample=False)
            uow.idempotency.complete(p.principal_id, "intake_confirm", self.context.idempotency_key,
                IntakeCommandResult(kind="IMPORT", identifier=receipt["import_id"], store=draft["store"]))
            uow.intake.delete("PREVIEW", identifier)
            return receipt

    def initialize_runtime(self):
        """명시적으로 동의한 관리자만, 기존 설정이 없는 조직에 안전한 초기값을 만듭니다."""
        from src.application.config.commands import SettingsCommands
        from src.domain.config.models import RuntimeConfig
        require(self.context.principal, "admin")
        config = RuntimeConfig(jev_enabled=True, auto_investigation=True, auto_rca_draft=True,
            auto_capa_draft=True, multi_agent_enabled=True, loop_enabled=True,
            allowed_agent_types=("HISTORY", "TRANSACTION", "INVENTORY"),
            allowed_tools=("voc.search", "transaction.search", "inventory.snapshot"))
        version = SettingsCommands(self.persistence, self.context, clock=self.clock).update(
            config, 0, "첫 실행: 외부 AI 및 외부 실행 없는 조사 설정")
        return {"config_version": version.config_version}

    def analyze(self, import_id, topic):
        """확인된 Import만 조사 대상으로 연결하며 임의 Agent/Prompt 입력을 받지 않습니다."""
        from src.ai.decision.service import ShadowDecisions
        from src.ai.workflow.runtime import HistoryWorkflows, WorkflowNotAllowed
        from src.domain.incidents.enums import Severity
        from src.domain.incidents.models import Evidence
        from src.domain.jobs.models import Job
        p, now = self.context.principal, self.clock()
        require(p, "operate")
        if not self.context.idempotency_key:
            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
        with self.persistence.transaction(p.tenant_id) as uow:
            receipt = uow.intake.get("IMPORT", import_id)
            if receipt is None:
                raise IncidentNotFound()
            require(p, "operate", receipt["store"])
            fingerprint = hashlib.sha256(json.dumps([import_id, topic]).encode()).hexdigest()
            uow.idempotency.claim(p.principal_id, "intake_analyze", self.context.idempotency_key, fingerprint)
            config = uow.configs.current()
            if not config or not config.config.jev_enabled or not config.config.auto_investigation:
                raise IncidentConflict("운영 설정에서 Jev와 자동 조사를 활성화해 주세요.")
            uow.intake.lock_store(receipt["store"])
            link = uow.intake.get("ANALYSIS", import_id)
            if link and link["topic"] != topic:
                raise IncidentConflict("이 Import의 조사 주제는 이미 고정되었습니다. 연결된 사건을 확인해 주세요.")
            identity = str(uuid5(NAMESPACE_URL, "intake-analysis:"+p.tenant_id+":"+import_id))
            if not link:
                commands = IncidentService(uow.incidents, self.clock, lambda: identity, p)
                incident = commands.create(topic, Severity.MEDIUM, receipt["store"], "데이터 담당자")
                incident = commands.triage(identity, expected_version=incident.version)
                incident = commands.investigate(identity, expected_version=incident.version)
                for index, ref in enumerate(receipt["source_refs"][:20]):
                    incident = commands.add_evidence(identity, Evidence("intake-ref-"+str(index), ref["source_ref"],
                        ref["agent_type"], "가져온 자료의 출처 참조", 1.0), expected_version=incident.version)
                link = {"import_id": import_id, "store": receipt["store"], "incident_id": identity, "topic": topic}
                uow.intake.put("ANALYSIS", import_id, receipt["store"], link)
                self.audit(uow, "first_incident", identity)
            snapshot_id = str(uuid5(NAMESPACE_URL, "intake-snapshot:"+identity))
            snapshot = uow.jobs.get(snapshot_id) or uow.jobs.save(Job(snapshot_id, p.tenant_id,
                "incident.snapshot", self.context.correlation_id, now, now, incident_id=identity, store=receipt["store"]))
            uow.idempotency.complete(p.principal_id, "intake_analyze", self.context.idempotency_key,
                IntakeCommandResult(kind="IMPORT", identifier=import_id, store=receipt["store"]))
            existing = uow.decisions.by_job(snapshot_id)
            job = uow.jobs.get(str(uuid5(NAMESPACE_URL, "history:"+p.tenant_id+":"+existing.decision_id))) if existing else None
            if job:
                return {"incident_id": identity, "job_id": job.job_id, "status": str(job.status)}
        decision = ShadowDecisions(self.persistence, clock=self.clock).record(snapshot)
        if decision is None:
            raise IncidentConflict("현재 정책에서 조사를 시작할 수 없습니다. 운영 설정을 확인해 주세요.")
        try:
            job = HistoryWorkflows(self.persistence, clock=self.clock).enqueue(self.context, identity, decision.decision_id)
        except WorkflowNotAllowed as exc:
            raise IncidentConflict("현재 사건 상태 또는 정책에서 자동 조사를 허용하지 않습니다.") from exc
        return {"incident_id": identity, "job_id": job.job_id, "status": str(job.status)}

    def _import(self, uow, records, store, *, sample):
        if not records or not any(r["kind"] != "매장" for r in records):
            raise ValueError("VOC 또는 관측 자료를 한 행 이상 입력해 주세요.")
        if any(r["store"] != store for r in records):
            raise AccessError()
        digest = hashlib.sha256(json.dumps([sample, records], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        uow.intake.lock_store(store)
        existing = uow.intake.get("IMPORT", digest)
        if existing:
            return existing
        refs = uow.intake.save_records(records, sample=sample)
        receipt = {"import_id": digest, "store": store, "sample": sample, "row_count": len(refs),
            "source_refs": refs, "created_at": self.clock().isoformat()}
        uow.intake.put("IMPORT", digest, store, receipt)
        self.audit(uow, "sample_import" if sample else "file_import", digest)
        return receipt

    def sample(self, store):
        """같은 조직/매장의 Demo 버전은 시각이 달라져도 한 번만 생성합니다."""
        p = self.context.principal
        require(p, "operate", store)
        if not self.context.idempotency_key:
            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
        if store not in self.status()["stores"]:
            raise IncidentNotFound()
        version = "demo-intake-1"
        identity = hashlib.sha256(json.dumps([store, version]).encode()).hexdigest()
        with self.persistence.transaction(p.tenant_id) as uow:
            cached = uow.idempotency.claim(p.principal_id, "intake_sample", self.context.idempotency_key, identity)
            if cached:
                return uow.intake.get("IMPORT", cached.identifier)
            uow.intake.lock_store(store)
            bundle = uow.intake.get("SAMPLE", identity)
            if bundle:
                receipt = uow.intake.get("IMPORT", bundle["import_id"])
            else:
                now = self.clock().isoformat()
                records = [{"kind": "VOC", "store": store, "source_id": f"demo-v1-voc-{n}",
                    "observed_at": now, "text": "품질 문제가 반복되어 메뉴 제공 상태 확인이 필요합니다.",
                    "rating": 1, "product": "체험 메뉴"} for n in (1, 2)]
                records.extend({"kind": kind, "store": store, "source_id": source,
                    "observed_at": now, "signal": signal} for kind, source, signal in (
                    ("판매_거래", "demo-v1-refund", "REFUND_SIGNAL"),
                    ("재고", "demo-v1-stock", "STOCK_SHORTAGE")))
                receipt = self._import(uow, records, store, sample=True)
                uow.intake.put("SAMPLE", identity, store, {"version": version, "import_id": receipt["import_id"]})
            uow.idempotency.complete(p.principal_id, "intake_sample", self.context.idempotency_key,
                IntakeCommandResult(kind="IMPORT", identifier=receipt["import_id"], store=store))
            return receipt
