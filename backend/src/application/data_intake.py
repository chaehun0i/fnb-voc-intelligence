"""첫 실행 상태는 서버의 매장/입력/사건 기록으로 계산합니다."""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.application.incidents.service import IncidentNotFound
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
        uow.audit.append(AuditRecord(hashlib.sha256((action+identifier+now.isoformat()).encode()).hexdigest(),
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
            return {"stores": sorted(stores), "has_data": has_data, "first_run": not has_data,
                "import_count": len(imports), "incident_count": len(incidents),
                "can_import": allowed(p, "operate"), "imports": [{k: i[k] for k in
                    ("import_id", "store", "sample", "row_count", "created_at")}
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
