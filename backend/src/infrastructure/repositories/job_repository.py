"""조직 조건과 낙관적 버전 검사를 저장소에서도 강제합니다."""
from copy import deepcopy
from dataclasses import replace

from psycopg.types.json import Jsonb

from src.application.ports.repositories import JobConflict
from src.infrastructure.job_codec import job_document, job_from_document


class MemoryJobRepository:
    def __init__(self, state, tenant_id):
        self.state, self.tenant_id = state, tenant_id

    def get(self, job_id):
        job = self.state.data.setdefault("jobs", {}).get(job_id)
        return deepcopy(job) if job and job.tenant_id == self.tenant_id else None

    def list(self, *, status=None, priority=None, job_type=None, incident_id=None,
             correlation_id=None, limit=100, offset=0):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("조회 범위를 확인해 주세요.")
        filters = {"status": status, "priority": priority, "job_type": job_type,
                   "incident_id": incident_id, "correlation_id": correlation_id}
        jobs = [deepcopy(job) for job in self.state.data.setdefault("jobs", {}).values()
                if job.tenant_id == self.tenant_id and all(value is None or getattr(job, key) == value for key, value in filters.items())]
        return sorted(jobs, key=lambda job: (job.created_at, job.job_id), reverse=True)[offset:offset + limit]

    def save(self, job):
        previous = self.get(job.job_id)
        records = self.state.data.setdefault("jobs", {})
        if job.tenant_id != self.tenant_id or (previous is None and job.job_id in records) or (previous.version if previous else 0) != job.version:
            raise JobConflict()
        if job.dispatch_id and any(other.dispatch_id == job.dispatch_id and other.job_id != job.job_id for other in records.values()):
            raise JobConflict()
        saved = replace(job, version=job.version + 1)
        records[job.job_id] = deepcopy(saved)
        return saved


class PostgresJobRepository:
    def __init__(self, connection, tenant_id):
        self.connection, self.tenant_id = connection, tenant_id

    def get(self, job_id):
        row = self.connection.execute("SELECT document FROM serviq_jobs WHERE job_id=%s AND tenant_id=%s", (job_id, self.tenant_id)).fetchone()
        return job_from_document(row[0]) if row else None

    def list(self, *, status=None, priority=None, job_type=None, incident_id=None,
             correlation_id=None, limit=100, offset=0):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("조회 범위를 확인해 주세요.")
        criteria, args = ["tenant_id=%s"], [self.tenant_id]
        for column, value in {"status": status, "priority": priority, "job_type": job_type,
                              "incident_id": incident_id, "correlation_id": correlation_id}.items():
            if value is not None:
                criteria.append(f"{column}=%s")
                args.append(value)
        rows = self.connection.execute("SELECT document FROM serviq_jobs WHERE " + " AND ".join(criteria) + " ORDER BY created_at DESC,job_id DESC LIMIT %s OFFSET %s", (*args, limit, offset)).fetchall()
        return [job_from_document(row[0]) for row in rows]

    def save(self, job):
        if job.tenant_id != self.tenant_id:
            raise JobConflict()
        saved = replace(job, version=job.version + 1)
        values = (saved.status, saved.priority, saved.attempt, saved.max_attempts,
                  saved.version, saved.available_at, saved.lease_until, Jsonb(job_document(saved)))
        if job.version == 0:
            row = self.connection.execute("""INSERT INTO serviq_jobs(status,priority,attempt,max_attempts,version,available_at,lease_until,document,
                job_id,tenant_id,job_type,incident_id,store,correlation_id,dispatch_id,parent_job_id,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING job_id""", (*values, job.job_id, job.tenant_id, job.job_type, job.incident_id, job.store, job.correlation_id, job.dispatch_id, job.parent_job_id, job.created_at)).fetchone()
        else:
            row = self.connection.execute("""UPDATE serviq_jobs SET status=%s,priority=%s,attempt=%s,max_attempts=%s,
                version=%s,available_at=%s,lease_until=%s,document=%s,updated_at=CURRENT_TIMESTAMP
                WHERE job_id=%s AND tenant_id=%s AND version=%s RETURNING job_id""", (*values, job.job_id, self.tenant_id, job.version)).fetchone()
        if row is None:
            raise JobConflict()
        return saved
