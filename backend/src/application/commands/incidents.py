"""보호된 HTTP 명령을 기존 서비스와 같은 트랜잭션 안에서 실행합니다."""

import hashlib
import json
from dataclasses import asdict, is_dataclass
from uuid import uuid4

import psycopg

from src.application.approvals.service import ApprovalService
from src.application.incidents.service import IncidentService
from src.application.security.authorization import require
from src.application.security.principal import AccessError
from src.domain.approvals.audit import AuditRecord

COMMANDS = frozenset({"create", "triage", "investigate", "add_evidence", "prepare_rca",
                      "propose_action", "request_approval", "approve", "reject",
                      "execute", "verify", "close", "reopen"})


class IncidentCommands:
    def __init__(self, original, persistence, context):
        self.original, self.persistence, self.context = original, persistence, context

    def _service(self, repository):
        return IncidentService(repository, self.original.clock,
                               self.original.id_generator, self.context.principal)

    def __getattr__(self, operation):
        if operation not in COMMANDS | {"list", "get", "workspace"}:
            raise AttributeError(operation)

        def invoke(*args, **kwargs):
            try:
                return self._invoke(operation, args, kwargs)
            except AccessError as exc:
                if operation in COMMANDS:
                    with self.persistence.transaction(self.context.principal.tenant_id) as uow:
                        if operation not in {"create"} and args:
                            resource = str(args[0])
                        else:
                            resource = ""
                        # 권한 거부만 감사하며 재시도 충돌은 업무 감사로 중복 기록하지 않습니다.
                        if exc.code == "AUTHORIZATION_DENIED":
                            self._audit(uow, operation, resource, "DENIED")
                raise
            except psycopg.errors.LockNotAvailable as exc:
                raise AccessError("PROCESSING", 409) from exc
        return invoke

    def _audit(self, uow, operation, resource_id, result, version=None):
        principal = self.context.principal
        uow.audit.append(AuditRecord(
            str(uuid4()), principal.tenant_id, principal.principal_id, operation,
            "incident", resource_id, result, self.context.request_id,
            self.context.correlation_id, self._service(uow.incidents)._now(), version,
        ))

    def _invoke(self, operation, args, kwargs):
            with self.persistence.transaction(self.context.principal.tenant_id) as uow:
                service = self._service(uow.incidents)
                approval = ApprovalService(service, uow.approvals, self.context)
                key = None
                if operation in COMMANDS:
                    if operation == "create":
                        require(self.context.principal, "operate", kwargs.get("store"))
                    else:
                        service._load(args[0], None, "review" if operation in {"approve", "reject"} else "operate")
                    key = self.context.idempotency_key
                    if key is None:
                        if self.context.principal.principal_id != "local-operator" or self.context.principal.tenant_id != "legacy-local":
                            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
                        key = str(uuid4())
                    canonical = json.dumps([args, kwargs], sort_keys=True, ensure_ascii=False,
                                           default=lambda value: asdict(value) if is_dataclass(value) else str(value))
                    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
                    cached = uow.idempotency.claim(self.context.principal.principal_id, operation, key, fingerprint)
                    if cached is not None:
                        return cached
                if operation == "request_approval":
                    result = approval.request(*args, **kwargs)
                elif operation in {"approve", "reject"}:
                    result = approval.decide_incident(args[0], operation, *args[1:], **kwargs)
                else:
                    if operation == "execute":
                        approval.require_effective(service._load(args[0], None))
                    result = getattr(service, operation)(*args, **kwargs)
                if operation in COMMANDS:
                    self._audit(uow, operation, result.id, "SUCCESS", result.version)
                    uow.idempotency.complete(self.context.principal.principal_id, operation, key, result)
                return result
