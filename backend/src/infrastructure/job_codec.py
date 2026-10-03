"""시간대와 Enum을 보존하는 작업 저장 문서 변환입니다."""
from dataclasses import asdict
from datetime import datetime

from src.domain.jobs.models import Job

TIME_FIELDS = ("created_at", "available_at", "started_at", "completed_at", "lease_until")


def job_document(job: Job) -> dict:
    document = asdict(job)
    for field in TIME_FIELDS:
        document[field] = document[field].isoformat() if document[field] is not None else None
    return document


def job_from_document(document: dict) -> Job:
    data = dict(document)
    for field in TIME_FIELDS:
        data[field] = datetime.fromisoformat(data[field]) if data.get(field) is not None else None
    return Job(**data)
