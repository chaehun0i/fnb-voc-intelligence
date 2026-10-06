"""실행 식별자는 재사용하고 단계 이력은 추가 전용으로 보존합니다."""
from psycopg.types.json import Jsonb

from src.ai.workflow.models import (
    AgentRun,
    AgentStep,
    InvestigationResult,
    RuntimeEvent,
    WorkflowStatus,
)
from src.application.security.principal import AccessError


def validate(run, previous, tenant):
    AgentRun.model_validate(run.model_dump(mode="json"))
    if run.tenant_id != tenant:
        raise AccessError()
    if previous:
        fields = ("tenant_id", "incident_id", "job_id", "workflow_id", "config_version",
                  "jev_decision_id", "workflow_version", "started_at", "requested_by",
                  "delegated_roles", "delegated_store_scope", "initial_incident_version")
        if any(getattr(run, f) != getattr(previous, f) for f in fields):
            raise ValueError("실행의 원본 참조와 설정 버전은 바꿀 수 없습니다.")
        if previous.status == WorkflowStatus.COMPLETED and previous != run:
            raise ValueError("완료된 실행은 변경할 수 없습니다.")
        if previous.state.selection is not None and (run.state.selection != previous.state.selection or run.state.contexts != previous.state.contexts):
            raise ValueError("INVESTIGATION_SNAPSHOT_IMMUTABLE")
        if run.manifest != previous.manifest:
            raise ValueError("MANIFEST_IMMUTABLE")
    if run.state.config_version != run.config_version or run.state.tenant_id != tenant:
        raise ValueError("실행 상태의 조직과 설정 버전을 확인해 주세요.")


class MemoryAgentRunRepository:
    def __init__(self, state, tenant_id):
        self.state, self.tenant_id = state, tenant_id

    def get(self, run_id):
        run = self.state.data.get("agent_runs", {}).get(run_id)
        return run if run and run.tenant_id == self.tenant_id else None

    def lock(self, run_id):
        # AccessPersistence holds its memory transaction lock.
        return self.get(run_id)

    def events(self, run_id):
        if self.get(run_id) is None:
            return []
        return list(self.state.data.get("runtime_events", {}).get((self.tenant_id, run_id), {}).values())

    def append_event(self, run_id, event):
        run = self.lock(run_id)
        validate_event(event, run)
        items = self.state.data.setdefault("runtime_events", {}).setdefault((self.tenant_id, run_id), {})
        stored = items.setdefault(event.event_id, event)
        if stored != event:
            raise ValueError("RUNTIME_EVENT_CONFLICT")
        return stored

    def by_job(self, job_id):
        return next((r for r in self.state.data.get("agent_runs", {}).values()
                     if r.tenant_id == self.tenant_id and r.job_id == job_id), None)

    def history(self, incident_id, limit=20, offset=0):
        runs = [r for r in self.state.data.get("agent_runs", {}).values()
                if r.tenant_id == self.tenant_id and r.incident_id == incident_id]
        return sorted(runs, key=lambda r: (r.started_at, r.agent_run_id), reverse=True)[offset:offset+limit]

    def save(self, run):
        previous = self.by_job(run.job_id)
        validate(run, previous, self.tenant_id)
        if previous and previous.agent_run_id != run.agent_run_id:
            return previous
        self.state.data.setdefault("agent_runs", {})[run.agent_run_id] = run
        return run

    def append_step(self, step):
        run = self.get(step.agent_run_id)
        if run is None:
            raise AccessError()
        validate_step(step, run)
        key = (self.tenant_id, step.agent_run_id, step.sequence, step.attempt)
        self.state.data.setdefault("agent_steps", {}).setdefault(key, step)

    def steps(self, run_id):
        return sorted((s for (tenant, rid, *_), s in self.state.data.get("agent_steps", {}).items()
                       if tenant == self.tenant_id and rid == run_id), key=lambda s: (s.sequence, s.attempt))

    def branch(self, run_id, agent_type):
        if self.get(run_id) is None:
            return None
        results = [e.result for e in self.events(run_id) if e.kind == "RESULT" and e.agent_type == agent_type]
        return results[-1] if results else self.state.data.get("investigation_branches", {}).get((self.tenant_id, run_id, agent_type))

    def append_branch(self, run_id, result):
        validate_branch(result, self.get(run_id))
        key = (self.tenant_id, run_id, result.agent_type)
        stored = self.state.data.setdefault("investigation_branches", {}).setdefault(key, result)
        if stored != result:
            raise ValueError("BRANCH_RESULT_CONFLICT")
        return stored


class PostgresAgentRunRepository:
    def __init__(self, connection, tenant_id):
        self.connection, self.tenant_id = connection, tenant_id

    def get(self, run_id):
        row = self.connection.execute("SELECT document FROM serviq_agent_runs WHERE tenant_id=%s AND agent_run_id::text=%s",
                                      (self.tenant_id, run_id)).fetchone()
        return AgentRun.model_validate(row[0]) if row else None

    def lock(self, run_id):
        row = self.connection.execute("SELECT document FROM serviq_agent_runs WHERE tenant_id=%s AND agent_run_id::text=%s FOR UPDATE",
            (self.tenant_id, run_id)).fetchone()
        return AgentRun.model_validate(row[0]) if row else None

    def events(self, run_id):
        rows = self.connection.execute("SELECT document FROM serviq_runtime_events WHERE tenant_id=%s AND agent_run_id::text=%s ORDER BY sequence",
            (self.tenant_id, run_id)).fetchall()
        return [RuntimeEvent.model_validate(r[0]) for r in rows]

    def append_event(self, run_id, event):
        run = self.lock(run_id)
        validate_event(event, run)
        previous = next((e for e in self.events(run_id) if e.event_id == event.event_id), None)
        if previous is not None:
            if previous != event:
                raise ValueError("RUNTIME_EVENT_CONFLICT")
            return previous
        self.connection.execute("""INSERT INTO serviq_runtime_events(tenant_id,agent_run_id,sequence,event_id,document)
            SELECT %s,%s,COALESCE(MAX(sequence),0)+1,%s,%s FROM serviq_runtime_events
            WHERE tenant_id=%s AND agent_run_id::text=%s""", (self.tenant_id, run_id, event.event_id,
            Jsonb(event.model_dump(mode="json")), self.tenant_id, run_id))
        return event

    def by_job(self, job_id):
        row = self.connection.execute("SELECT document FROM serviq_agent_runs WHERE tenant_id=%s AND job_id=%s",
                                      (self.tenant_id, job_id)).fetchone()
        return AgentRun.model_validate(row[0]) if row else None

    def history(self, incident_id, limit=20, offset=0):
        rows = self.connection.execute("SELECT document FROM serviq_agent_runs WHERE tenant_id=%s AND incident_id=%s ORDER BY started_at DESC,agent_run_id DESC LIMIT %s OFFSET %s",
                                       (self.tenant_id, incident_id, limit, offset)).fetchall()
        return [AgentRun.model_validate(r[0]) for r in rows]

    def save(self, run):
        previous = self.by_job(run.job_id)
        validate(run, previous, self.tenant_id)
        if previous and previous.agent_run_id != run.agent_run_id:
            return previous
        document = Jsonb(run.model_dump(mode="json"))
        if previous:
            self.connection.execute("UPDATE serviq_agent_runs SET document=%s WHERE tenant_id=%s AND agent_run_id=%s",
                                    (document, self.tenant_id, run.agent_run_id))
        else:
            self.connection.execute("""INSERT INTO serviq_agent_runs(agent_run_id,tenant_id,incident_id,job_id,
                workflow_id,config_version,jev_decision_id,started_at,document) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(tenant_id,job_id) DO NOTHING""", (run.agent_run_id, self.tenant_id,
                run.incident_id, run.job_id, run.workflow_id, run.config_version,
                run.jev_decision_id, run.started_at, document))
        return self.by_job(run.job_id)

    def append_step(self, step):
        run = self.get(step.agent_run_id)
        if run is None:
            raise AccessError()
        validate_step(step, run)
        self.connection.execute("""INSERT INTO serviq_agent_steps(tenant_id,agent_run_id,sequence,attempt,document)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", (self.tenant_id, step.agent_run_id,
            step.sequence, step.attempt, Jsonb(step.model_dump(mode="json"))))

    def steps(self, run_id):
        rows = self.connection.execute("SELECT document FROM serviq_agent_steps WHERE tenant_id=%s AND agent_run_id::text=%s ORDER BY sequence,attempt",
                                      (self.tenant_id, run_id)).fetchall()
        return [AgentStep.model_validate(r[0]) for r in rows]

    def branch(self, run_id, agent_type):
        results = [e.result for e in self.events(run_id) if e.kind == "RESULT" and e.agent_type == agent_type]
        if results:
            return results[-1]
        row = self.connection.execute("SELECT document FROM serviq_investigation_branches WHERE tenant_id=%s AND agent_run_id::text=%s AND agent_type=%s",
            (self.tenant_id, run_id, agent_type)).fetchone()
        return InvestigationResult.model_validate(row[0]) if row else None

    def append_branch(self, run_id, result):
        validate_branch(result, self.get(run_id))
        self.connection.execute("INSERT INTO serviq_investigation_branches(tenant_id,agent_run_id,agent_type,document) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (self.tenant_id, run_id, result.agent_type, Jsonb(result.model_dump(mode="json"))))
        stored = self.branch(run_id, result.agent_type)
        if stored != result:
            raise ValueError("BRANCH_RESULT_CONFLICT")
        return stored


def validate_branch(result, run):
    from uuid import NAMESPACE_URL, uuid5
    if run is None:
        raise AccessError()
    result = InvestigationResult.model_validate(result.model_dump(mode="json"))
    pack = next((c for c in run.state.contexts if c.agent_type == result.agent_type), None)
    if (pack is None or result.tenant_id != run.tenant_id or result.incident_id != run.incident_id
            or result.store != pack.store or result.context_digest != pack.digest
            or result.branch_id != str(uuid5(NAMESPACE_URL, run.agent_run_id+":"+result.agent_type))):
        raise AccessError()


def validate_event(event, run):
    RuntimeEvent.model_validate(event.model_dump(mode="json"))
    if run is None:
        raise AccessError()
    if event.result is not None:
        validate_branch(event.result, run)


def validate_step(step, run):
    AgentStep.model_validate(step.model_dump(mode="json"))
    if step.result is not None:
        AgentRun.model_validate(run.model_copy(update={"state": step.result,
            "status": WorkflowStatus.RUNNING}).model_dump(mode="json"))
