"""작업 원본과 서버 권한을 운영 화면 계약으로 투영합니다."""
from src.application.security.authorization import allowed, require
from src.domain.jobs.models import JobStatus


class JobNotFound(Exception):
    """다른 조직의 작업도 존재하지 않는 작업과 동일하게 응답합니다."""


def permissions(job, principal):
    operator = allowed(principal, "operate", job.store)
    result = {}
    for action, statuses in {"retry": {JobStatus.FAILED, JobStatus.DLQ}, "cancel": {JobStatus.PENDING}}.items():
        permitted = operator and job.status in statuses
        reason = "처리할 수 있습니다." if permitted else (
            "현재 역할 또는 매장 범위에서는 처리할 수 없습니다." if not operator else
            "실행 중인 작업은 안전한 중단을 지원하지 않습니다." if job.status == JobStatus.RUNNING and action == "cancel" else
            "현재 작업 상태에서는 처리할 수 없습니다.")
        result[action] = {"allowed": permitted, "reason": reason}
    return result


def job_response(job, principal):
    return {
        "id": job.job_id, "tenant_id": job.tenant_id, "type": job.job_type,
        "status": job.status, "priority": job.priority, "queued_at": job.created_at.isoformat(),
        "attempts": job.attempt, "max_attempts": job.max_attempts,
        "incident_id": job.incident_id, "correlation_id": job.correlation_id,
        "config_version": job.config_version, "version": job.version,
        "parent_job_id": job.parent_job_id, "available_at": job.available_at,
        "started_at": job.started_at, "completed_at": job.completed_at,
        "lease_until": job.lease_until, "error_code": job.error_code,
        "error_summary": job.error_summary, "actions": permissions(job, principal),
    }


class JobQueries:
    def __init__(self, repository, principal):
        self.repository, self.principal = repository, principal

    def get_job(self, job_id):
        require(self.principal, "read")
        job = self.repository.get(job_id)
        if job is None:
            raise JobNotFound()
        require(self.principal, "read", job.store)
        return job

    def get(self, job_id):
        return job_response(self.get_job(job_id), self.principal)

    def list(self, **filters):
        require(self.principal, "read")
        return [job_response(job, self.principal) for job in self.repository.list(**filters)
                if allowed(self.principal, "read", job.store)]
