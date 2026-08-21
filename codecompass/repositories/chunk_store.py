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
        max_per_file: int = 1,
    ) -> list[tuple[Chunk, float]]:
        """Nearest chunks by cosine distance, closest first.

        Over-fetches, then caps how many chunks any one file may occupy: three
        chunks from the same file crowd out three other files that might have
        held the answer.
        """
        stmt = (
            select(
                Chunk,
                Chunk.embedding.cosine_distance(query_vector).label("distance"),
            )
            .where(
                Chunk.repository_id == repository_id,
                Chunk.embedding.is_not(None),
            )
            .order_by("distance")
            .limit(limit * 4)
        )

        results: list[tuple[Chunk, float]] = []
        per_file: dict[uuid.UUID, int] = {}

        for chunk, distance in self._session.execute(stmt).all():
            seen = per_file.get(chunk.source_file_id, 0)
            if seen >= max_per_file:
                continue

            per_file[chunk.source_file_id] = seen + 1
            results.append((chunk, distance))

            if len(results) == limit:
                break

        return results