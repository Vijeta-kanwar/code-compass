from types import SimpleNamespace

from codecompass.services.answer_service import extract_citations


def make_chunk(path, start_line, end_line):
    return SimpleNamespace(
        source_file=SimpleNamespace(path=path),
        start_line=start_line,
        end_line=end_line,
    )


def test_invalid_citation_number_is_dropped():
    used_chunks = [
        make_chunk("src/one.py", 1, 5),
        make_chunk("src/two.py", 10, 15),
    ]

    citations = extract_citations(
        "The answer cites [1] and invents [3].",
        used_chunks,
    )

    assert citations == [
        {
            "n": 1,
            "file_path": "src/one.py",
            "start_line": 1,
            "end_line": 5,
        }
    ]


def test_duplicate_citations_are_deduplicated():
    used_chunks = [
        make_chunk("src/one.py", 1, 5),
        make_chunk("src/two.py", 10, 15),
    ]

    citations = extract_citations(
        "The answer cites [1], [1], and [2].",
        used_chunks,
    )

    assert [citation["n"] for citation in citations] == [1, 2]


def test_zero_citation_number_is_dropped():
    used_chunks = [
        make_chunk("src/one.py", 1, 5),
    ]

    citations = extract_citations("[0] is not a valid citation.", used_chunks)

    assert citations == []
