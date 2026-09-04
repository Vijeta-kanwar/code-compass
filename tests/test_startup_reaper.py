import asyncio
import uuid

from codecompass.db import SessionLocal
from codecompass.main import lifespan
from codecompass.models import IndexingJob, Repository


def test_startup_reaper_marks_active_job_failed():
    repository_id = uuid.uuid4()
    job_id = uuid.uuid4()

    with SessionLocal() as session:
        repository = Repository(
            id=repository_id,
            url=f"https://github.com/test/reaper-{repository_id}",
            name=f"reaper-{repository_id}",
        )

        session.add(repository)
        session.flush()

        job = IndexingJob(
            id=job_id,
            repository_id=repository_id,
            status="embedding",
        )

        session.add(job)
        session.commit()

    try:
        async def run_lifespan():
            async with lifespan(None):
                pass

        asyncio.run(run_lifespan())

        with SessionLocal() as session:
            job = session.get(IndexingJob, job_id)

            assert job is not None
            assert job.status == "failed"
            assert job.error_message == "interrupted by process restart"
            assert job.finished_at is not None

    finally:
        with SessionLocal() as session:
            repository = session.get(Repository, repository_id)
            if repository is not None:
                session.delete(repository)
                session.commit()
