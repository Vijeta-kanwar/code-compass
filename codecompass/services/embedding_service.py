import logging
import uuid
import time

from sqlalchemy.orm import Session

from codecompass.config import get_settings
from codecompass.embedding.client import QuotaExhausted, embed_documents
from codecompass.repositories.chunk_store import ChunkStore

logger = logging.getLogger(__name__)


def embed_pending_chunks(
    session: Session,
    repository_id: uuid.UUID,
) -> int:
    """Embed every chunk of this repository that has no vector yet."""

    settings = get_settings()
    store = ChunkStore(session)

    embedded_total = 0
    poisoned: set[uuid.UUID] = set()

    while True:
        batch = store.next_unembedded_batch(
            repository_id,
            settings.embedding_batch_size,
        )

        if not batch:
            break

        # Don't repeatedly process chunks that have already failed
        # during this run.
        batch = [chunk for chunk in batch if chunk.id not in poisoned]

        if not batch:
            # We fetched only poisoned chunks.
            # Without this guard we'd loop forever.
            logger.warning(
                "No embeddable chunks remain in the current batch "
                "for repository %s",
                repository_id,
            )
            break

        # Empty/whitespace-only text cannot be sent to Gemini.
        usable = [
            chunk
            for chunk in batch
            if chunk.embedded_text and chunk.embedded_text.strip()
        ]

        for chunk in batch:
            if not chunk.embedded_text or not chunk.embedded_text.strip():
                logger.warning(
                    "chunk %s has no embeddable text",
                    chunk.id,
                )
                poisoned.add(chunk.id)

        if not usable:
            continue

        embedded_total += _embed_batch(session, usable, poisoned)

        # Pace ourselves rather than sprinting into a 429 and backing off —
        # free-tier quota is the binding constraint here, not throughput.
        time.sleep(settings.embedding_batch_delay_seconds)
    return embedded_total


def _embed_batch(session: Session, batch: list, poisoned: set[uuid.UUID]) -> int:
    """Embed one batch, halving on failure to isolate a bad chunk.

    A batch can fail for two very different reasons: the whole request was too
    large, or one chunk inside it is unembeddable. Splitting tells them apart
    without needing to know which happened.
    """
    try:
        vectors = embed_documents([c.embedded_text for c in batch])

        # If the API returns a different count than we sent, zip would pair every
        # chunk with its neighbour's vector — no crash, just silently wrong
        # retrieval forever. Cheapest possible guard against the worst bug here.
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"asked for {len(batch)} embeddings, got {len(vectors)}"
            )

        for chunk, vector in zip(batch, vectors):
            chunk.embedding = vector

        # Commit per batch, not at the end: a crash costs one batch of API calls
        # rather than the entire repository's worth.
        session.commit()
        return len(batch)

    except QuotaExhausted:
        # Not our problem to solve here — the caller decides what an exhausted
        # daily quota means for the job as a whole.
        raise

    except Exception as exc:
        session.rollback()

        if len(batch) == 1:
            # Isolated and still failing, so this one chunk is the problem.
            # Leave its embedding NULL and move on; a later run can retry it.
            logger.warning("chunk %s could not be embedded: %s", batch[0].id, exc)
            poisoned.add(batch[0].id)
            return 0

        logger.warning("batch of %d failed (%s), splitting", len(batch), exc)
        mid = len(batch) // 2
        return (
            _embed_batch(session, batch[:mid], poisoned)
            + _embed_batch(session, batch[mid:], poisoned)
        )
    

