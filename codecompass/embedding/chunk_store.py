def next_unembedded_batch(
        self,
        repository_id: uuid.UUID,
        limit: int,
        exclude_ids: set[uuid.UUID] | None = None,
    ) -> list[Chunk]:
        """Oldest-first so a resumed job makes forward progress.

        exclude_ids holds chunks that failed earlier in this run — without it,
        one poisonous chunk gets handed back on every iteration forever.
        """
        query = select(Chunk).where(
            Chunk.repository_id == repository_id, Chunk.embedding.is_(None)
        )
        if exclude_ids:
            query = query.where(Chunk.id.notin_(exclude_ids))

        return list(self._session.scalars(query.order_by(Chunk.id).limit(limit)))