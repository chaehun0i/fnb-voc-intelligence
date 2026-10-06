"""조직별 설정 버전 추가와 동시 수정 충돌을 처리합니다."""
from copy import deepcopy

from psycopg.types.json import Jsonb

from src.application.ports.repositories import ConfigVersionConflict
from src.application.security.principal import AccessError
from src.domain.config.models import (
    ConfigVersion,
    config_document,
    config_from_document,
)


def check_append(version, tenant_id, expected_version, current):
    if version.tenant_id != tenant_id:
        raise AccessError()
    actual = current.config_version if current else 0
    if actual != expected_version:
        raise ConfigVersionConflict()
    if (version.config_version != actual + 1 or version.parent_version != (actual or None)
            or version.created_at.tzinfo is None or not version.reason.strip()):
        raise ValueError("설정 버전·부모·시각·사유를 확인해 주세요.")


class MemoryConfigRepository:
    def __init__(self, state, tenant_id):
        self.state, self.tenant_id = state, tenant_id

    def history(self, limit=100, offset=0):
        items = [item for item in self.state.data.get("configs", {}).values() if item.tenant_id == self.tenant_id]
        return deepcopy(sorted(items, key=lambda item: item.config_version, reverse=True)[offset:offset+limit])

    def current(self):
        return next(iter(self.history(1)), None)

    def get(self, version):
        return deepcopy(self.state.data.get("configs", {}).get((self.tenant_id, version)))

    def append(self, version, expected_version):
        check_append(version, self.tenant_id, expected_version, self.current())
        if version.rollback_source is not None and self.get(version.rollback_source) is None:
            raise ValueError("복원 원본 버전이 필요합니다.")
        self.state.data.setdefault("configs", {})[(self.tenant_id, version.config_version)] = deepcopy(version)
        return deepcopy(version)


class PostgresConfigRepository:
    def __init__(self, connection, tenant_id):
        self.connection, self.tenant_id = connection, tenant_id

    @staticmethod
    def _decode(row):
        return ConfigVersion(row[0], row[1], config_from_document(row[2]), row[3], row[4], row[5], row[6], row[7], row[8]) if row else None

    def history(self, limit=100, offset=0):
        rows = self.connection.execute("""SELECT config_version,tenant_id,config_json,reason,created_by,
            created_at,parent_version,rollback_source,scope FROM serviq_config_versions
            WHERE tenant_id=%s ORDER BY config_version DESC LIMIT %s OFFSET %s""",
            (self.tenant_id, limit, offset)).fetchall()
        return [self._decode(row) for row in rows]

    def current(self):
        return next(iter(self.history(1)), None)

    def get(self, version):
        row = self.connection.execute("""SELECT config_version,tenant_id,config_json,reason,created_by,
            created_at,parent_version,rollback_source,scope FROM serviq_config_versions
            WHERE tenant_id=%s AND config_version=%s""", (self.tenant_id, version)).fetchone()
        return self._decode(row)

    def append(self, version, expected_version):
        # 첫 버전의 동시 생성까지 조직 잠금과 유일성으로 보호합니다.
        self.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("config:"+self.tenant_id,))
        check_append(version, self.tenant_id, expected_version, self.current())
        if version.rollback_source is not None and self.get(version.rollback_source) is None:
            raise ValueError("복원 원본 버전이 필요합니다.")
        self.connection.execute("""INSERT INTO serviq_config_versions(tenant_id,config_version,scope,
            config_json,reason,created_by,created_at,parent_version,rollback_source)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (self.tenant_id, version.config_version,
            version.scope, Jsonb(config_document(version.config)), version.reason, version.created_by,
            version.created_at, version.parent_version, version.rollback_source))
        return version
