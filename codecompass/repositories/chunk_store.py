import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager

from codecompass.models import Chunk


class ChunkStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def count_unembedded(self, repository_id: uuid.UUID) -> int:
        return self._session.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.repository_id == repository_id,
                Chunk.embedding.is_(None),
            )
        ) or 0

    def next_unembedded_batch(
        self,
        repository_id: uuid.UUID,
        limit: int,
    ) -> list[Chunk]:
        """Oldest-first so a resumed job makes forward progress rather than
        re-picking the same rows.
        """
        return list(
            self._session.scalars(
                select(Chunk)
                .where(
                    Chunk.repository_id == repository_id,
                    Chunk.embedding.is_(None),
                )
                .order_by(Chunk.id)
                .limit(limit)
            )
        )

    def search_by_vector(
        self,
        repository_id: uuid.UUID,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[tuple[Chunk, float]]:
        """Nearest chunks by cosine distance, closest first."""

        stmt = (
            select(
                Chunk,
                Chunk.embedding.cosine_distance(query_vector).label("distance"),
            )
            .join(Chunk.source_file)
            .options(contains_eager(Chunk.source_file))
            .where(
                Chunk.repository_id == repository_id,
                Chunk.embedding.is_not(None),
            )
            .order_by("distance")
            .limit(limit)
        )

        return list(self._session.execute(stmt).unique().all())