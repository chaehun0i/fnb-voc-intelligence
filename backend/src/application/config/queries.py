"""조직별 설정 조회·출처·필드 차이를 서버에서 계산합니다."""
import json

import psycopg

from src.application.ports.config_repository import SettingsUnavailable
from src.application.security.authorization import allowed, require
from src.domain.config.models import RuntimeConfig, config_document
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed


def config_diff(before: RuntimeConfig, after: RuntimeConfig) -> list[dict]:
    previous, following = config_document(before), config_document(after)
    def flatten(document):
        return {path: value for key, item in document.items()
                for path, value in (([(key + "." + child, child_value) for child, child_value in item.items()])
                                    if isinstance(item, dict) else [(key, item)])}
    left, right = flatten(previous), flatten(following)
    return [{"field": key, "before": json.dumps(left[key], ensure_ascii=False),
             "after": json.dumps(right[key], ensure_ascii=False)} for key in sorted(right) if left[key] != right[key]]


def workspace(version, principal, resolver):
    raw = version.config if version else RuntimeConfig()
    resolved = resolver.resolve(raw, source="TENANT" if version else "PLATFORM_DEFAULT")
    permission = {"allowed": allowed(principal, "admin"), "reason": "HQ_ADMIN만 조직 운영 설정을 변경할 수 있습니다."}
    return {
        "config": {**config_document(raw), "version": version.config_version if version else 0},
        "effective": config_document(resolved.effective), "sources": dict(resolved.sources),
        "adjusted_fields": list(resolved.adjusted_fields), "runtime_status": resolved.runtime_status,
        "current": {"created_at": version.created_at.isoformat() if version else None,
                    "created_by": version.created_by if version else None,
                    "reason": version.reason if version else "아직 저장된 버전이 없습니다. 플랫폼 기본값입니다.",
                    "parent_version": version.parent_version if version else None},
        "rules": resolver.field_rules(), "save_permission": permission, "rollback_permission": permission,
        "scope": "TENANT",
    }


class SettingsQueries:
    def __init__(self, persistence, principal, resolver=None):
        self.persistence, self.principal = persistence, principal
        self.resolver = resolver or ConfigResolver()

    def current(self):
        require(self.principal, "read")
        try:
            with self.persistence.transaction(self.principal.tenant_id) as uow:
                return workspace(uow.configs.current(), self.principal, self.resolver)
        except (psycopg.Error, ValueError, TypeError, KeyError, ConfigValidationFailed) as error:
            raise SettingsUnavailable() from error

    def history(self, limit=20, offset=0):
        require(self.principal, "read")
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 10000:
            raise ValueError("이력 조회 범위를 확인해 주세요.")
        try:
            with self.persistence.transaction(self.principal.tenant_id) as uow:
                versions = uow.configs.history(limit+1, offset)
                items = []
                for version in versions[:limit]:
                    parent = uow.configs.get(version.parent_version) if version.parent_version else None
                    items.append({"version": version.config_version, "parent_version": version.parent_version,
                                  "rollback_source": version.rollback_source, "actor": version.created_by,
                                  "created_at": version.created_at.isoformat(), "reason": version.reason,
                                  "snapshot": config_document(version.config),
                                  "changes": config_diff(parent.config if parent else RuntimeConfig(), version.config)})
                return {"revisions": items, "limit": limit, "offset": offset, "has_more": len(versions) > limit}
        except (psycopg.Error, ValueError, TypeError, KeyError) as error:
            raise SettingsUnavailable() from error
