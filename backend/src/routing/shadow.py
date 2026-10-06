"""Job의 업무 효과와 분리된 Shadow 판단 경계입니다."""
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

import psycopg

from src.domain.approvals.audit import AuditRecord
from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed
from src.domain.incidents.enums import Severity
from src.routing.context import build_context
from src.routing.engine import JevEngine
from src.routing.models import (
    DecisionReasonCode,
    DecisionRecord,
    DecisionResult,
    DecisionRoute,
    DecisionValidationError,
)

logger = logging.getLogger(__name__)


class ShadowDecisions:
    def __init__(self, persistence, *, engine=None, resolver=None, clock=None, id_generator=None):
        self.persistence = persistence
        self.engine = engine or JevEngine()
        self.resolver = resolver or ConfigResolver()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_generator = id_generator or (lambda: str(uuid4()))

    def record(self, job):
        if job.job_type != "incident.snapshot":
            return None
        try:
            with self.persistence.transaction(job.tenant_id) as uow:
                if uow.connection is not None:
                    uow.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("jev:"+job.tenant_id+":"+job.job_id,))
                existing = uow.decisions.by_job(job.job_id)
                if existing is not None:
                    return existing
                incident = uow.incidents.get(job.incident_id)
                if incident is None or incident.store != job.store:
                    raise DecisionValidationError("DECISION_TARGET_INVALID")
                version = uow.configs.current()
                raw = version.config if version else RuntimeConfig()
                if not raw.jev_enabled:
                    return None
                config_version = version.config_version if version else 0
                start, failure = perf_counter(), None
                # digest 최소 입력은 참조/버전뿐이며 원문·PII·임의 예외 문자열은 제외합니다.
                digest_facts = {"tenant": job.tenant_id, "incident": incident.id, "incident_version": incident.version, "config_version": config_version}
                try:
                    resolved = self.resolver.resolve(raw)
                    context = build_context(incident, resolved, config_version)
                    digest_facts["normalized"] = asdict(context)
                    result = self.engine.evaluate(context)
                except (DecisionValidationError, ConfigValidationFailed, ValueError, TypeError):
                    failure = "DECISION_VALIDATION_ERROR"
                    result = self._fallback(incident, config_version)
                except Exception:  # noqa: BLE001 - 원문 대신 stable 실패 감사를 남기는 Shadow 경계입니다.
                    failure = "DECISION_INTERNAL_ERROR"
                    result = self._fallback(incident, config_version)
                digest = hashlib.sha256(json.dumps(digest_facts, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
                record = DecisionRecord(self.id_generator(), job.tenant_id, incident.id, job.job_id,
                    result, digest, self.clock(), max(0, (perf_counter()-start)*1000), incident.version, failure)
                saved = uow.decisions.append(record)
                uow.audit.append(AuditRecord(str(uuid4()), job.tenant_id, "job-worker", "jev_shadow", "decision",
                    saved.decision_id, "FAILED" if failure else "SUCCESS", job.job_id, job.correlation_id,
                    saved.decided_at.isoformat(), incident.version, failure))
                if failure:
                    logger.error("Jev Shadow 실패 code=%s job_id=%s", failure, job.job_id)
                return saved
        except (psycopg.Error, DecisionValidationError):
            # 저장 불가도 관측 가능하게 남깁니다. 기존 업무 상태를 실패로 바꾸지 않습니다.
            logger.error("Jev Shadow 기록 불가 code=DECISION_PERSISTENCE_UNAVAILABLE job_id=%s", job.job_id)
            return None

    @staticmethod
    def _fallback(incident, config_version):
        return DecisionResult(DecisionRoute.MANUAL_REVIEW, Severity.CRITICAL, incident.priority, (),
            False, True, "manual-safe-v1", "small", "판단 실패로 수동 검토가 필요합니다.",
            (DecisionReasonCode.ENGINE_FAILURE,), config_version)
