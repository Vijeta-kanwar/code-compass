import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from codecompass.models import ACTIVE_STATUSES, IndexingJob


class JobStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, job_id: uuid.UUID) -> IndexingJob | None:
        return self._session.get(IndexingJob, job_id)

    def active_for_repository(self, repository_id: uuid.UUID) -> IndexingJob | None:
        return self._session.scalar(
            select(IndexingJob).where(
                IndexingJob.repository_id == repository_id,
                IndexingJob.status.in_(ACTIVE_STATUSES),
            )
        )

    def create(self, repository_id: uuid.UUID) -> IndexingJob:
        job = IndexingJob(repository_id=repository_id, status="pending")
        self._session.add(job)
        self._session.flush()
        return job

    def mark_failed(self, job: IndexingJob, reason: str) -> None:
        job.status = "failed"
        job.error_message = reason[:2000]   # cap it; tracebacks can be enormous
        job.finished_at = datetime.now(timezone.utc)