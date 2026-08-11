import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from codecompass.models import Chunk


class ChunkStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def count_unembedded(self, repository_id: uuid.UUID) -> int:
        return self._session.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.repository_id == repository_id, Chunk.embedding.is_(None)
            )
        ) or 0

    def next_unembedded_batch(self, repository_id: uuid.UUID, limit: int) -> list[Chunk]:
        """Oldest-first so a resumed job makes forward progress rather than
        re-picking the same rows."""
        return list(
            self._session.scalars(
                select(Chunk)
                .where(Chunk.repository_id == repository_id, Chunk.embedding.is_(None))
                .order_by(Chunk.id)
                .limit(limit)
            )
        )