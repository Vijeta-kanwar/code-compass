from types import SimpleNamespace

from codecompass.services.fusion import reciprocal_rank_fusion


def make_chunk(chunk_id):
    return SimpleNamespace(id=chunk_id)


def test_chunk_appearing_in_both_lists_ranks_first():
    chunk_a = make_chunk(1)
    chunk_b = make_chunk(2)
    chunk_c = make_chunk(3)

    ranked_lists = [
        [chunk_a, chunk_b],
        [chunk_c, chunk_a],
    ]

    result = reciprocal_rank_fusion(ranked_lists)

    assert result == [chunk_a, chunk_c, chunk_b]


def test_duplicate_chunks_are_returned_once():
    chunk_a = make_chunk(1)
    chunk_b = make_chunk(2)

    ranked_lists = [
        [chunk_a, chunk_b],
        [chunk_a],
    ]

    result = reciprocal_rank_fusion(ranked_lists)

    assert result == [chunk_a, chunk_b]


def test_limit_truncates_fused_results():
    chunks = [make_chunk(1), make_chunk(2), make_chunk(3)]

    result = reciprocal_rank_fusion([chunks], limit=2)

    assert result == chunks[:2]
