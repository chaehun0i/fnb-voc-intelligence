"""설정 변경 의도는 snapshot 원문 없이 버전 참조로 남깁니다."""
from copy import deepcopy

from psycopg.types.json import Jsonb


class ConfigEvents:
    def __init__(self, tenant_id, *, connection=None, state=None):
        self.tenant_id, self.connection, self.state = tenant_id, connection, state

    def append(self, version, event_id, correlation_id):
        if version.tenant_id != self.tenant_id:
            raise ValueError("설정 이벤트 조직이 일치하지 않습니다.")
        payload = {"event_id": event_id, "event_type": "config.changed", "event_version": 1,
                   "resource_type": "runtime_config", "aggregate_id": self.tenant_id + ":runtime",
                   "aggregate_version": version.config_version, "tenant_id": self.tenant_id,
                   "correlation_id": correlation_id, "occurred_at": version.created_at.isoformat(),
                   "parent_version": version.parent_version, "rollback_source": version.rollback_source}
        if self.connection is not None:
            self.connection.execute("""INSERT INTO serviq_outbox(event_id,incident_id,event_type,payload,tenant_id)
                VALUES(%s,NULL,'config.changed',%s,%s)""", (event_id, Jsonb(payload), self.tenant_id))
        else:
            self.state.data.setdefault("config_events", []).append(deepcopy(payload))
