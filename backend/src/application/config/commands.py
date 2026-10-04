"""설정 변경·감사·이벤트·멱등성 결과를 하나의 업무 트랜잭션으로 기록합니다."""
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import psycopg

from src.application.ports.config_repository import SettingsUnavailable
from src.application.security.authorization import require
from src.application.security.principal import AccessError
from src.domain.approvals.audit import AuditRecord
from src.domain.config.models import ConfigVersion, config_document
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed


class SettingsCommands:
    def __init__(self, persistence, context, resolver=None, clock=None):
        self.persistence, self.context = persistence, context
        self.resolver = resolver or ConfigResolver()
        self.clock = clock or (lambda: datetime.now(UTC))

    def _audit(self, uow, action, result, reason=None, version=None, target=None):
        principal = self.context.principal
        uow.audit.append(AuditRecord(str(uuid4()), principal.tenant_id, principal.principal_id,
            "config_" + action, "runtime_config", principal.tenant_id + ":runtime" + (f":rollback:{target}" if target else ""),
            result, self.context.request_id, self.context.correlation_id,
            self.clock().isoformat(), version, reason))

    def update(self, config, expected_version, reason):
        return self._execute("update", expected_version, reason, config=config)

    def _execute(self, action, expected_version, reason, *, config=None, target=None):
        principal = self.context.principal
        try:
            require(principal, "admin")
            if type(expected_version) is not int or expected_version < 0 or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
                raise ConfigValidationFailed([{"field": "reason/expected_version", "type": "INPUT", "reason": "현재 버전과 변경 사유(1~1000자)가 필요합니다."}])
            key = self.context.idempotency_key
            if key is None:
                raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
            fingerprint = hashlib.sha256(json.dumps({"action": action, "expected_version": expected_version,
                "reason": reason.strip(), "target": target, "config": config_document(config) if config else None},
                sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            with self.persistence.transaction(principal.tenant_id) as uow:
                cached = uow.idempotency.claim(principal.principal_id, "config_" + action, key, fingerprint)
                if cached is not None:
                    # 현재 상한이 달라진 경우 과거 replay도 안전 검증을 통과해야 합니다.
                    self.resolver.resolve(cached.config)
                    return cached
                self.resolver.resolve(config)
                now = self.clock()
                if now.tzinfo is None:
                    raise ValueError("설정 기록 시각에는 시간대가 필요합니다.")
                version = ConfigVersion(expected_version+1, principal.tenant_id, config, reason.strip(),
                    principal.principal_id, now.astimezone(UTC), expected_version or None, target)
                saved = uow.configs.append(version, expected_version)
                self._audit(uow, action, "SUCCESS", reason.strip(), saved.config_version, target)
                uow.config_events.append(saved, str(uuid4()), self.context.correlation_id)
                uow.idempotency.complete(principal.principal_id, "config_" + action, key, saved)
                return saved
        except AccessError as error:
            if error.code == "AUTHORIZATION_DENIED":
                with self.persistence.transaction(principal.tenant_id) as uow:
                    self._audit(uow, action, "DENIED")
            raise
        except psycopg.errors.LockNotAvailable as error:
            raise AccessError("PROCESSING", 409) from error
        except psycopg.Error as error:
            raise SettingsUnavailable() from error
