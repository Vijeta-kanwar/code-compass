import uuid

from sqlalchemy.orm import Session

from codecompass.embedding.client import QuotaExhausted, embed_query
from codecompass.repositories.chunk_store import ChunkStore


def search_repository(
    session: Session,
    repository_id: uuid.UUID,
    query: str,
    limit: int = 10,
) -> list[tuple]:
    """Search a repository using semantic vector similarity."""

    try:
        query_vector = embed_query(query)
    except QuotaExhausted:
        raise

    store = ChunkStore(session)

    return store.search_by_vector(
        repository_id=repository_id,
        query_vector=query_vector,
        limit=limit,
    )