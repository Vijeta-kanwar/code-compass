import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from codecompass.config import get_settings
from codecompass.db import SessionLocal
from codecompass.ingestion.git_clone import CloneFailed, shallow_clone
from codecompass.ingestion.walker import walk_python_files
from codecompass.models import IndexingJob, Repository
from codecompass.repositories.file_store import FileStore

logger = logging.getLogger(__name__)


def chunk_file(content: str, path: str) -> list:
    """Placeholder — Day 4 fills this in. Returning [] keeps the pipeline runnable."""
    return []


def run_indexing_job(job_id: uuid.UUID, repository_id: uuid.UUID) -> None:
    """Background entrypoint.

    Takes UUIDs, not ORM objects: this runs after the HTTP response, so anything
    attached to the request's session is already closed. It opens its own.
    """
    settings = get_settings()
    session = SessionLocal()
    clone_path = Path(settings.clone_dir) / str(repository_id)

    try:
        job = session.get(IndexingJob, job_id)
        repo = session.get(Repository, repository_id)
        if job is None or repo is None:
            logger.error("job %s or repo %s vanished before start", job_id, repository_id)
            return

        job.status = "cloning"
        session.commit()

        commit_sha = shallow_clone(repo.url, clone_path)
        job.commit_sha = commit_sha

        # Idempotency: same commit as last time means there is nothing to do.
        if repo.last_indexed_commit == commit_sha:
            job.status = "ready"
            job.finished_at = datetime.now(timezone.utc)
            session.commit()
            return

        job.status = "parsing"
        session.commit()

        store = FileStore(session)
        known_hashes = store.hashes_for_repository(repository_id)
        seen_paths: set[str] = set()

        for walked in walk_python_files(clone_path):
            seen_paths.add(walked.path)
            job.files_seen += 1

            if known_hashes.get(walked.path) == walked.sha256:
                job.files_skipped += 1
                continue

            # One transaction per file, in this order:
            #   delete stale chunks -> write new chunks -> stamp the hash.
            # The hash is a promise that the chunks exist, so it lands last.
            file = store.upsert(
                repository_id=repository_id, path=walked.path, language="python",
                sha256=walked.sha256, line_count=walked.line_count,
            )
            store.delete_chunks(file.id)

            for chunk in chunk_file(walked.content, walked.path):
                session.add(chunk)
                job.chunks_created += 1

            file.content_sha256 = walked.sha256
            job.files_indexed += 1
            session.commit()

        removed = store.delete_files_not_in(repository_id, seen_paths)
        logger.info("job %s removed %d deleted files", job_id, removed)

        repo.last_indexed_commit = commit_sha
        job.status = "ready"
        job.finished_at = datetime.now(timezone.utc)
        session.commit()

    except CloneFailed as exc:
        # An expected failure with a message worth showing the user.
        _fail(session, job_id, str(exc))
    except Exception as exc:
        # Unexpected: log the traceback for us, store a short reason for them.
        logger.exception("indexing job %s failed", job_id)
        _fail(session, job_id, f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(clone_path, ignore_errors=True)
        session.close()


def _fail(session, job_id: uuid.UUID, reason: str) -> None:
    """Record the failure on its own clean transaction.

    The session may be mid-rollback when we get here, so discard whatever was
    pending before writing. A job that dies without a stored reason is a job
    nobody can debug.
    """
    session.rollback()
    job = session.get(IndexingJob, job_id)
    if job is not None:
        job.status = "failed"
        job.error_message = reason[:2000]
        job.finished_at = datetime.now(timezone.utc)
        session.commit()