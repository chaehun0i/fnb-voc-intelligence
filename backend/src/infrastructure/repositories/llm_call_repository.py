"""원문을 받을 수 없는 typed 기록만 조직별로 저장합니다."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime

from psycopg.types.json import Jsonb

from src.ai.intelligence.models import LLMCallRecord
from src.application.security.principal import AccessError


def validate(record, tenant):
    if record.tenant_id != tenant:
        raise AccessError()
    if record.created_at.tzinfo is None:
        raise ValueError("기록 시각의 시간대가 필요합니다.")


def document(record):
    return {**asdict(record), "created_at": record.created_at.isoformat()}


def decode(value):
    return LLMCallRecord(**{**value, "created_at": datetime.fromisoformat(value["created_at"])})


class MemoryLLMCallRepository:
    def __init__(self, state, tenant_id):
        self.state, self.tenant_id = state, tenant_id

    def append(self, record):
        validate(record, self.tenant_id)
        items = self.state.data.setdefault("llm_calls", {})
        if record.call_id in items:
            raise ValueError("이미 기록된 호출입니다.")
        items[record.call_id] = deepcopy(record)

    def history(self, incident_id, limit=20):
        rows = [item for item in self.state.data.get("llm_calls", {}).values()
            if item.tenant_id == self.tenant_id and item.incident_id == incident_id]
        return deepcopy(sorted(rows, key=lambda item: (item.created_at, item.call_id), reverse=True)[:limit])


class PostgresLLMCallRepository:
    def __init__(self, connection, tenant_id):
        self.connection, self.tenant_id = connection, tenant_id

    def append(self, record):
        validate(record, self.tenant_id)
        self.connection.execute("""INSERT INTO serviq_llm_calls(call_id,tenant_id,incident_id,config_version,created_at,document)
            VALUES(%s,%s,%s,%s,%s,%s)""", (record.call_id, self.tenant_id, record.incident_id,
                record.config_version, record.created_at, Jsonb(document(record))))

    def history(self, incident_id, limit=20):
        rows = self.connection.execute("""SELECT document FROM serviq_llm_calls WHERE tenant_id=%s AND incident_id=%s
            ORDER BY created_at DESC,call_id DESC LIMIT %s""", (self.tenant_id, incident_id, limit)).fetchall()
        return [decode(row[0]) for row in rows]
