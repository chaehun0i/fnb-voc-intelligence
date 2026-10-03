"""작업 운영 변경과 감사·멱등성 결과를 같은 트랜잭션으로 기록합니다."""
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import psycopg

from src.application.jobs.queries import JobQueries
from src.application.ports.job_repository import JobConflict
from src.application.security.authorization import require
from src.application.security.principal import AccessError
from src.domain.approvals.audit import AuditRecord
from src.domain.jobs.models import cancel, retry


class JobCommands:
    def __init__(self, persistence, context, clock=None, id_generator=None):
        self.persistence, self.context = persistence, context
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_generator = id_generator or (lambda: str(uuid4()))

    def _audit(self, uow, action, job_id, result, version=None, reason=None):
        principal = self.context.principal
        uow.audit.append(AuditRecord(str(uuid4()), principal.tenant_id, principal.principal_id,
            "job_" + action, "job", job_id, result, self.context.request_id,
            self.context.correlation_id, self.clock().isoformat(), version, reason))

    def execute(self, action, job_id, reason, expected_version):
        if action not in {"retry", "cancel"} or not reason.strip():
            raise ValueError("작업 명령과 사유를 확인해 주세요.")
        principal = self.context.principal
        try:
            with self.persistence.transaction(principal.tenant_id) as uow:
                original = JobQueries(uow.jobs, principal).get_job(job_id)
                # Replay도 현재 요청자의 조직·역할·매장 검사를 우회하지 않습니다.
                require(principal, "operate", original.store)
                key = self.context.idempotency_key
                if key is None:
                    raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
                fingerprint = hashlib.sha256(json.dumps([action, job_id, reason.strip(), expected_version],
                    ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                cached = uow.idempotency.claim(principal.principal_id, "job_" + action, key, fingerprint)
                if cached is not None:
                    return cached
                if original.version != expected_version:
                    raise JobConflict()
                now = self.clock()
                changed = retry(original, self.id_generator(), now) if action == "retry" else cancel(original, now)
                saved = uow.jobs.save(changed)
                self._audit(uow, action, original.job_id, "SUCCESS", saved.version, reason.strip())
                uow.idempotency.complete(principal.principal_id, "job_" + action, key, saved)
                return saved
        except AccessError as error:
            if error.code == "AUTHORIZATION_DENIED":
                with self.persistence.transaction(principal.tenant_id) as uow:
                    self._audit(uow, action, job_id, "DENIED")
            raise
        except psycopg.errors.LockNotAvailable as error:
            raise AccessError("PROCESSING", 409) from error
