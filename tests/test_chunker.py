from pathlib import Path

import pytest

from codecompass.parsing.chunker import chunk_python_file

FIXTURE = Path(__file__).parent / "fixtures" / "sample.py"
SOURCE = FIXTURE.read_text()
CHUNKS = chunk_python_file(SOURCE, "fixtures/sample.py")


def test_round_trip():
    """Every chunk's content must be exactly its own line range.

    This one test catches every off-by-one you can make today.
    """
    lines = SOURCE.splitlines()
    for c in CHUNKS:
        assert "\n".join(lines[c.start_line - 1 : c.end_line]) == c.content, c.symbol_name


def test_async_functions_are_not_lost():
    assert any(c.symbol_name == "fetch" for c in CHUNKS)
    assert any(c.symbol_name == "Widget.refresh" for c in CHUNKS)


def test_decorators_are_included():
    label = next(c for c in CHUNKS if c.symbol_name == "Widget.label")
    assert label.content.lstrip().startswith("@")


def test_header_never_leaks_into_content():
    for c in CHUNKS:
        assert "File:" not in c.content


def test_methods_do_not_overlap_each_other():
    methods = sorted(
        (c for c in CHUNKS if c.kind == "method"), key=lambda c: c.start_line
    )
    for a, b in zip(methods, methods[1:]):
        assert a.end_line < b.start_line, f"{a.symbol_name} overlaps {b.symbol_name}"


def test_class_chunk_excludes_method_bodies():
    widget = next(c for c in CHUNKS if c.kind == "class" and c.symbol_name == "Widget")
    assert "def __init__" not in widget.content


def test_no_empty_chunks():
    for c in CHUNKS:
        assert c.content.strip()


def test_broken_syntax_returns_empty():
    assert chunk_python_file("def f(:\n    pass", "bad.py") == []


def test_line_ranges_are_sane():
    for c in CHUNKS:
        assert c.start_line >= 1
        assert c.end_line >= c.start_line

def test_file_without_defs_still_produces_a_chunk():
    """Config and constants modules are exactly where 'what's the default X'
    questions land — excluding them would be a silent retrieval hole."""
    src = (Path(__file__).parent / "fixtures" / "config_only.py").read_text()
    chunks = chunk_python_file(src, "fixtures/config_only.py")
    assert len(chunks) == 1
    assert chunks[0].kind == "module"
    assert "TIMEOUT" in chunks[0].content