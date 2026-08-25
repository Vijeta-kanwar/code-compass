RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list],
    k: int = RRF_K,
    limit: int = 5,
) -> list:
    """Merge ranked lists by rank position, discarding original scores.

    Rank starts at 1. Higher RRF score means a better final rank.
    """
    scores: dict = {}
    chunks: dict = {}

    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            chunk_id = chunk.id

            scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                1.0 / (k + rank)
            )
            chunks[chunk_id] = chunk

    ranked = sorted(
        scores,
        key=lambda chunk_id: (-scores[chunk_id], chunk_id),
    )

    return [chunks[chunk_id] for chunk_id in ranked[:limit]]