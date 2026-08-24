import uuid

from sqlalchemy.orm import Session

from codecompass.embedding.client import QuotaExhausted, embed_query
from codecompass.repositories.chunk_store import ChunkStore
from codecompass.services.fusion import reciprocal_rank_fusion


def search_repository(
    session: Session,
    repository_id: uuid.UUID,
    query: str,
    limit: int = 10,
    mode: str = "hybrid",
) -> list[tuple]:
    """Search a repository using vector or hybrid retrieval."""

    store = ChunkStore(session)

    if mode == "vector":
        try:
            query_vector = embed_query(query)
        except QuotaExhausted:
            raise

        return store.search_by_vector(
            repository_id=repository_id,
            query_vector=query_vector,
            limit=limit,
        )

    if mode == "hybrid":
        try:
            query_vector = embed_query(query)
        except QuotaExhausted:
            raise

        # Raw vector results for fusion — no per-file dedup yet.
        vector_results = store.search_by_vector(
            repository_id=repository_id,
            query_vector=query_vector,
            limit=20,
            max_per_file=20,
        )

        # Raw lexical results for fusion.
        text_results = store.search_by_text(
            repository_id=repository_id,
            query=query,
            limit=20,
        )

        ranked_lists = [
            [chunk for chunk, _ in vector_results],
            [chunk for chunk, _ in text_results],
        ]

        # Get extra candidates because per-file dedup happens afterward.
        fused_chunks = reciprocal_rank_fusion(
            ranked_lists=ranked_lists,
            limit=limit * 4,
        )

        # Deduplicate by source file AFTER fusion.
        final_chunks = []
        per_file: dict[uuid.UUID, int] = {}

        for chunk in fused_chunks:
            seen = per_file.get(chunk.source_file_id, 0)

            if seen >= 1:
                continue

            per_file[chunk.source_file_id] = seen + 1
            final_chunks.append(chunk)

            if len(final_chunks) == limit:
                break

        # Existing API expects a (Chunk, score) tuple.
        # RRF does not produce a cosine distance, so score is currently 0.0.
        return [(chunk, 0.0) for chunk in final_chunks]

    raise ValueError(f"Unsupported search mode: {mode}")