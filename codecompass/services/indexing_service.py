import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from codecompass.config import get_settings
from codecompass.db import SessionLocal
from codecompass.ingestion.git_clone import CloneFailed, shallow_clone
from codecompass.ingestion.walker import walk_python_files
from codecompass.models import Chunk, IndexingJob, Repository
from codecompass.parsing.chunker import chunk_python_file
from codecompass.repositories.file_store import FileStore
from codecompass.embedding.client import QuotaExhausted
from codecompass.services.embedding_service import embed_pending_chunks


logger = logging.getLogger(__name__)




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
        # Idempotency: same commit as last time means there is nothing to do
        # only when the indexed chunks still exist.
        has_chunks = session.query(Chunk.id).filter(
            Chunk.repository_id == repository_id
        ).first() is not None
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

            # Content unchanged since last index — nothing to re-parse or re-embed.
            if known_hashes.get(walked.path) == walked.sha256:
                job.files_skipped += 1
                continue

            # One transaction per file, in this order:
            #   upsert -> delete stale chunks -> write new chunks -> stamp the hash.
            # The hash is a promise that the chunks exist, so it lands last.
            file = store.upsert(
                repository_id=repository_id,
                path=walked.path,
                language="python",
                sha256=walked.sha256,
                line_count=walked.line_count,
            )
            store.delete_chunks(file.id)

            # The parser returns plain dataclasses — it has no idea what a
            # repository_id is. Mapping to ORM rows happens here, in the layer
            # that does know.
            for parsed in chunk_python_file(walked.content, walked.path):
                session.add(
                    Chunk(
                        source_file_id=file.id,
                        repository_id=repository_id,
                        symbol_name=parsed.symbol_name,
                        kind=parsed.kind,
                        start_line=parsed.start_line,
                        end_line=parsed.end_line,
                        content=parsed.content,
                        embedded_text=parsed.embedded_text,
                        token_count=parsed.token_count,
                    )
                )
                job.chunks_created += 1

            file.content_sha256 = walked.sha256
            job.files_indexed += 1
            session.commit()
        removed = store.delete_files_not_in(repository_id, seen_paths)
        logger.info("job %s removed %d deleted files", job_id, removed)
        job.status = "embedding"
        session.commit()

        embedded = embed_pending_chunks(session, repository_id)
        logger.info("job %s embedded %d chunks", job_id, embedded)

        repo.last_indexed_commit = commit_sha
        job.status = "ready"
        job.finished_at = datetime.now(timezone.utc)
        session.commit()

    except CloneFailed as exc:
        # An expected failure with a message worth showing the user.
        _fail(session, job_id, str(exc))
    except QuotaExhausted as exc:
        # Honest status: the work isn't done, but re-POSTing resumes from
        # exactly the chunks that are still NULL.
        _fail(session, job_id, f"{exc} Re-run to resume.")
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