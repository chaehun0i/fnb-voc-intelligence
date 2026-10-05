"""Outbox 전달과 독립 Job 실행을 함께 구동하되 상태 저장은 분리합니다."""
import argparse
import logging
import os
import signal
import threading

import psycopg

from src.application.decisions.shadow import ShadowDecisions
from src.application.workflows.history import HISTORY_JOB
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.history_search import PostgresHistorySearch
from src.infrastructure.outbox.job_dispatch import PostgresJobDispatcher
from src.infrastructure.outbox.worker import OutboxWorker, _positive_seconds
from src.infrastructure.queue.worker import JobWorker
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)
from src.runtime.workflows.checkpoint import postgres_checkpoint
from src.runtime.workflows.processor import HistoryProcessor

logger = logging.getLogger(__name__)


def snapshot_processor(repository, shadow=None, history=None):
    def process(job):
        if job.job_type == HISTORY_JOB and history is not None:
            return history(job)
        if job.job_type != "incident.snapshot":
            raise ValueError("지원하지 않는 작업 종류입니다.")
        incident = repository.get(job.incident_id, tenant_id=job.tenant_id)
        if incident is None or incident.store != job.store:
            raise ValueError("작업 대상의 조직과 매장 계약을 확인해 주세요.")
        # 외부 조치 없이 원본 계약을 확인하므로 중복 인수에도 업무 효과가 발생하지 않습니다.
        logger.info("Job 계약 확인 job_id=%s correlation_id=%s", job.job_id, job.correlation_id)
        if shadow is not None:
            shadow.record(job)
    return process


class QueueRuntime:
    def __init__(self, outbox, jobs):
        self.outbox, self.jobs = outbox, jobs

    def run_once(self):
        dispatched = self.outbox.run_once()
        executed = self.jobs.run_once()
        return dispatched or executed

    def run(self, stop, poll_seconds):
        while not stop.is_set():
            if not self.run_once():
                stop.wait(poll_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Outbox를 전달하고 독립 Job을 실행합니다.")
    parser.add_argument("--once", action="store_true", help="전달·실행을 각각 최대 한 건 수행합니다.")
    parser.add_argument("--poll-seconds", type=_positive_seconds, default=2)
    parser.add_argument("--lease-seconds", type=_positive_seconds, default=60)
    arguments = parser.parse_args(argv)
    dsn = os.getenv("SERVIQ_DATABASE_URL")
    if not dsn:
        raise SystemExit("SERVIQ_DATABASE_URL을 설정해 주세요.")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stop, previous = threading.Event(), {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, lambda *_: stop.set())
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            repository = PostgresIncidentRepository(dsn)
            persistence = AccessPersistence(repository)
            history = HistoryProcessor(persistence, PostgresHistorySearch(dsn),
                lambda: postgres_checkpoint(dsn), dsn=dsn, lease_seconds=arguments.lease_seconds)
            runtime = QueueRuntime(
                OutboxWorker(connection, PostgresJobDispatcher(connection, repository), lease_seconds=arguments.lease_seconds),
                JobWorker(connection, snapshot_processor(repository, ShadowDecisions(persistence), history), lease_seconds=arguments.lease_seconds))
            if arguments.once:
                runtime.run_once()
            else:
                runtime.run(stop, arguments.poll_seconds)
    except psycopg.Error:
        raise SystemExit("작업 저장소 연결을 확인해 주세요. 잠금 만료 후 안전하게 재인수할 수 있습니다.") from None
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    main()
