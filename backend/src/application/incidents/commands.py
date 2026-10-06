"""보호된 HTTP 명령을 기존 서비스와 같은 트랜잭션 안에서 실행합니다."""

import hashlib
import json
from dataclasses import asdict, is_dataclass
from uuid import uuid4

import psycopg

from src.ai.execution.policy import validate_approval
from src.ai.workflow.runtime import enqueue_resume
from src.application.approvals.service import ApprovalService
from src.application.incidents.service import IncidentNotFound, IncidentService
from src.application.ports.repositories import IncidentConflict
from src.application.security.authorization import require
from src.application.security.principal import AccessError
from src.domain.approvals.audit import AuditRecord
from src.domain.incidents.transitions import DomainRuleViolation

COMMANDS = frozenset({"create", "triage", "investigate", "add_evidence", "prepare_rca",
                      "propose_action", "request_approval", "approve", "reject",
                      "execute", "verify", "close", "reopen", "review_approve", "review_reject"})


class IncidentCommands:
    def __init__(self, original, persistence, context):
        self.original, self.persistence, self.context = original, persistence, context

    def _service(self, repository):
        return IncidentService(repository, self.original.clock,
                               self.original.id_generator, self.context.principal)

    def _command(self, operation, *args, **kwargs):
        try:
            return self._invoke(operation, args, kwargs)
        except AccessError as exc:
            if operation in COMMANDS:
                with self.persistence.transaction(self.context.principal.tenant_id) as uow:
                    resource = str(args[0]) if operation != "create" and args else ""
                    # 권한 거부만 감사하며 재시도 충돌은 업무 감사로 중복 기록하지 않습니다.
                    if exc.code == "AUTHORIZATION_DENIED":
                        self._audit(uow, operation, resource, "DENIED")
            raise
        except psycopg.errors.LockNotAvailable as exc:
            raise AccessError("PROCESSING", 409) from exc

    def create(self, *args, **kwargs):
        return self._command("create", *args, **kwargs)

    def triage(self, *args, **kwargs):
        return self._command("triage", *args, **kwargs)

    def investigate(self, *args, **kwargs):
        return self._command("investigate", *args, **kwargs)

    def add_evidence(self, *args, **kwargs):
        return self._command("add_evidence", *args, **kwargs)

    def prepare_rca(self, *args, **kwargs):
        return self._command("prepare_rca", *args, **kwargs)

    def propose_action(self, *args, **kwargs):
        return self._command("propose_action", *args, **kwargs)

    def request_approval(self, *args, **kwargs):
        return self._command("request_approval", *args, **kwargs)

    def approve(self, *args, **kwargs):
        return self._command("approve", *args, **kwargs)

    def reject(self, *args, **kwargs):
        return self._command("reject", *args, **kwargs)

    def execute(self, *args, **kwargs):
        return self._command("execute", *args, **kwargs)

    def verify(self, *args, **kwargs):
        return self._command("verify", *args, **kwargs)

    def close(self, *args, **kwargs):
        return self._command("close", *args, **kwargs)

    def reopen(self, *args, **kwargs):
        return self._command("reopen", *args, **kwargs)

    def review_approve(self, *args, **kwargs):
        return self._command("review_approve", *args, **kwargs)

    def review_reject(self, *args, **kwargs):
        return self._command("review_reject", *args, **kwargs)

    def list(self, *args, **kwargs):
        return self._command("list", *args, **kwargs)

    def get(self, *args, **kwargs):
        return self._command("get", *args, **kwargs)

    def workspace(self, *args, **kwargs):
        return self._command("workspace", *args, **kwargs)

    def _audit(self, uow, operation, resource_id, result, version=None):
        principal = self.context.principal
        uow.audit.append(AuditRecord(
            str(uuid4()), principal.tenant_id, principal.principal_id, operation,
            "approval" if operation.startswith("review_") else "incident", resource_id, result, self.context.request_id,
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
                    elif operation.startswith("review_"):
                        target = uow.approvals.get(args[0])
                        if target is None:
                            raise IncidentNotFound()
                        service._load(target.incident_id, None, "review")
                    else:
                        service._load(args[0], None, "review" if operation in {"approve", "reject"} else "operate")
                    key = self.context.idempotency_key
                    if key is None:
                        if operation.startswith("review_") or self.context.principal.authentication_source != "local-compatibility":
                            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
                        key = str(uuid4())
                    canonical = json.dumps([args, kwargs], sort_keys=True, ensure_ascii=False,
                                           default=lambda value: asdict(value) if is_dataclass(value) else str(value))
                    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
                    cached = uow.idempotency.claim(self.context.principal.principal_id, operation, key, fingerprint)
                    if cached is not None:
                        return cached
                if operation.startswith("review_"):
                    if target.agent_run_id:
                        validate_approval(uow, target, service.clock())
                    result = approval.decide(args[0], operation.removeprefix("review_"), *args[1:], **kwargs)
                    if target.agent_run_id:
                        enqueue_resume(uow, uow.approvals.get(target.approval_id), service.clock())
                elif operation == "request_approval":
                    result = approval.request(*args, **kwargs)
                elif operation in {"approve", "reject"}:
                    result = approval.decide_incident(args[0], operation, *args[1:], **kwargs)
                else:
                    if operation == "execute":
                        approval.require_effective(service._load(args[0], None))
                    result = getattr(service, operation)(*args, **kwargs)
                if operation in COMMANDS:
                    self._audit(uow, operation, args[0] if operation.startswith("review_") else result.id, "SUCCESS", result.version)
                    uow.idempotency.complete(self.context.principal.principal_id, operation, key, result)
                if operation == "workspace" and result["commands"]["execute"]["allowed"]:
                    try:
                        approval.require_effective(service.get(args[0]))
                    except (IncidentConflict, DomainRuleViolation):
                        permission = {"allowed": False, "reason": "유효한 승인 기록과 검토 기한을 확인해 주세요."}
                        result["commands"]["execute"] = permission
                        result["actions"]["execute"] = permission
                return result
