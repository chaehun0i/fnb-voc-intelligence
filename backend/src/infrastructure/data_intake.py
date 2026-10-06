"""데이터 입력 문서만 저장합니다. 원문은 AgentRun/감사/Checkpoint에 복제하지 않습니다."""
import hashlib
import json
from copy import deepcopy
from datetime import datetime

from psycopg.types.json import Jsonb

from src.ai.workflow.models import OperationalObservation
from src.application.ports.repositories import IncidentConflict


class IntakeRepository:
    def __init__(self, tenant_id, memory, connection=None):
        self.tenant_id, self.memory, self.connection = tenant_id, memory, connection

    def get(self, kind, identifier, *, lock=False):
        if self.connection:
            suffix = " FOR UPDATE" if lock else ""
            row = self.connection.execute("SELECT document FROM serviq_data_intake WHERE tenant_id=%s AND kind=%s AND resource_id=%s"+suffix,
                (self.tenant_id, kind, identifier)).fetchone()
            return row[0] if row else None
        return deepcopy(self.memory.data.get("intake", {}).get((self.tenant_id, kind, identifier)))

    def list(self, kind):
        if self.connection:
            return [r[0] for r in self.connection.execute("SELECT document FROM serviq_data_intake WHERE tenant_id=%s AND kind=%s ORDER BY resource_id LIMIT 1000",
                (self.tenant_id, kind)).fetchall()]
        return [deepcopy(v) for (tenant, k, _), v in self.memory.data.get("intake", {}).items()
            if tenant == self.tenant_id and k == kind][:1000]

    def put(self, kind, identifier, store, document):
        if self.connection:
            self.connection.execute("INSERT INTO serviq_data_intake(tenant_id,kind,resource_id,store,document) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (self.tenant_id, kind, identifier, store, Jsonb(document)))
        else:
            self.memory.data.setdefault("intake", {}).setdefault((self.tenant_id, kind, identifier), deepcopy(document))
        return self.get(kind, identifier)

    def delete(self, kind, identifier):
        if self.connection:
            self.connection.execute("DELETE FROM serviq_data_intake WHERE tenant_id=%s AND kind=%s AND resource_id=%s",
                (self.tenant_id, kind, identifier))
        else:
            self.memory.data.setdefault("intake", {}).pop((self.tenant_id, kind, identifier), None)

    def lock_store(self, store):
        if self.connection:
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("intake:"+self.tenant_id+":"+store,))

    def expire_previews(self, now):
        if self.connection:
            self.connection.execute("DELETE FROM serviq_data_intake WHERE tenant_id=%s AND kind='PREVIEW' AND (document->>'expires_at')::timestamptz <= %s",
                (self.tenant_id, now))
        else:
            for item in self.list("PREVIEW"):
                if datetime.fromisoformat(item["expires_at"]) <= now:
                    self.delete("PREVIEW", item["preview_id"])

    def save_records(self, records, *, sample):
        refs = []
        for record in records:
            if record["kind"] == "매장":
                continue
            identity = hashlib.sha256(json.dumps([self.tenant_id, record["store"], record["kind"], record["source_id"]]).encode()).hexdigest()[:32]
            document = {**record, "sample": sample}
            previous = self.get("SOURCE", identity)
            if previous is not None and previous != document:
                raise IncidentConflict("같은 자료ID의 기존 값을 덮어쓸 수 없습니다.")
            self.put("SOURCE", identity, record["store"], document)
            agent = "HISTORY" if record["kind"] == "VOC" else "TRANSACTION" if record["kind"] == "판매_거래" else "INVENTORY"
            ref = ("review" if agent == "HISTORY" else agent.lower())+":intake-"+identity
            refs.append({"source_ref": ref, "agent_type": agent})
            if agent != "HISTORY":
                observation = OperationalObservation(tenant_id=self.tenant_id, store=record["store"], agent_type=agent,
                    source_ref=ref, observed_at=datetime.fromisoformat(record["observed_at"]), signal=record["signal"],
                    source="SYNTHETIC_OPERATIONAL_FIXTURE" if sample else "FILE_IMPORTED_OBSERVATION")
                if self.connection:
                    self.connection.execute("INSERT INTO serviq_operational_observations(tenant_id,store,agent_type,source_ref,observed_at,document) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (self.tenant_id, record["store"], agent, ref, observation.observed_at, Jsonb(observation.model_dump(mode="json"))))
        return refs

    def require_separate_dataset(self, store, sample):
        if self.connection:
            conflict = self.connection.execute("SELECT EXISTS(SELECT 1 FROM serviq_data_intake WHERE tenant_id=%s AND kind='SOURCE' AND store=%s AND (document->>'sample')::boolean IS DISTINCT FROM %s)",
                (self.tenant_id, store, sample)).fetchone()[0]
        else:
            conflict = any(r["store"] == store and r["sample"] != sample for r in self.list("SOURCE"))
        if conflict or (sample and store in self.source_stores()):
            raise IncidentConflict("Demo와 운영 자료는 같은 매장에 혼합하지 않습니다. 별도의 체험 매장 또는 운영 매장을 선택해 주세요.")

    def source_stores(self):
        if self.connection:
            return [r[0] for r in self.connection.execute("SELECT DISTINCT store FROM serviq_history_sources WHERE tenant_id=%s UNION SELECT DISTINCT store FROM serviq_operational_observations WHERE tenant_id=%s",
                (self.tenant_id, self.tenant_id)).fetchall()]
        return list({s["store"] for s in self.list("SOURCE")})
