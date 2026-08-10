import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_CHUNK_TOKENS = 1500


@dataclass(frozen=True)
class ParsedChunk:
    symbol_name: str | None   # "Session.get", "get_encoding", None for module
    kind: str                  # module | class | function | method
    start_line: int            # 1-based, inclusive
    end_line: int              # 1-based, inclusive
    content: str               # raw source slice — no header, ever
    embedded_text: str         # context header + content
    token_count: int


def chunk_python_file(content: str, path: str) -> list[ParsedChunk]:
    """
    Split one Python file into retrievable units.

    Returns [] rather than raising on unparseable input.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        logger.warning("skipping unparseable file %s", path)
        return []

    # Match the test convention: split without keeping newline characters,
    # then reconstruct source with "\n".
    lines = content.splitlines()

    first_def = next(
        (
            _node_start_line(n)
            for n in tree.body
            if isinstance(
                n,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            )
        ),
        None,
    )

    # If there is no class/function, keep the whole file as a module chunk.
    # This preserves useful files such as config.py, constants.py,
    # and __init__.py instead of silently dropping them.
    if first_def is None:
        if not content.strip():
            return []

        content_slice = _source_range(lines, 1, len(lines))

        if not content_slice.strip():
            return []

        return [
            ParsedChunk(
                symbol_name=None,
                kind="module",
                start_line=1,
                end_line=len(lines),
                content=content_slice,
                embedded_text=content_slice,
                token_count=_estimate_tokens(content_slice),
            )
        ]

    # Module preamble is everything before the first class/function.
    end_line = first_def - 1

    if end_line < 1:
        return []

    content_slice = _source_range(lines, 1, end_line)

    # Don't create whitespace-only chunks.
    if not content_slice.strip():
        return []

    chunks: list[ParsedChunk] = []

    if content_slice.strip():
        chunks.append(
            ParsedChunk(
                symbol_name=None,
                kind="module",
                start_line=1,
                end_line=end_line,
                content=content_slice,
                embedded_text=content_slice,
                token_count=_estimate_tokens(content_slice),
            )
        )

    for node in tree.body:
        # AsyncFunctionDef is a sibling of FunctionDef, not a subclass —
        # leave it out of this tuple and every `async def` disappears.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunks.append(_build_def_chunk(node, lines, node.name, "function"))
        elif isinstance(node, ast.ClassDef):
            methods = [
                child for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]

            # The class chunk stops where its first method starts. Including the
            # method bodies would duplicate every method that's already its own
            # chunk — double the embedding calls, and one fat chunk that matches
            # everything vaguely.
            class_start = _node_start_line(node)
            class_end = (
                _node_start_line(methods[0]) - 1 if methods else node.end_lineno
            )

            if class_end >= class_start:
                class_content = _source_range(lines, class_start, class_end)
                if class_content.strip():
                    chunks.append(
                        ParsedChunk(
                            symbol_name=node.name,
                            kind="class",
                            start_line=class_start,
                            end_line=class_end,
                            content=class_content,
                            embedded_text=class_content,
                            token_count=_estimate_tokens(class_content),
                        )
                    )

            for method in methods:
                chunks.append(
                    _build_def_chunk(
                        method, lines, f"{node.name}.{method.name}", "method"
                    )
                )
    return sorted(chunks, key=lambda c: c.start_line)


def _estimate_tokens(text: str) -> int:
    # ~4 chars per token. Deliberately a heuristic: calling the real tokenizer
    # per chunk would burn free-tier quota we need for actual embedding.
    return len(text) // 4


def _source_range(lines: list[str], start: int, end: int) -> str:
    """Slice by 1-based inclusive line numbers, the way ast reports them."""
    return "\n".join(lines[start - 1:end])


def _node_start_line(node: ast.AST) -> int:
    """First line of the node including its decorators."""
    line = node.lineno

    decorators = getattr(node, "decorator_list", [])
    if decorators:
        line = min(line, *(d.lineno for d in decorators))

    return line

def _build_def_chunk(node, lines, symbol_name: str, kind: str) -> ParsedChunk:
    """Turn one def/async def node into a chunk.

    Shared by top-level functions and class methods — the only difference
    between them is the name and the kind, so it lives in one place.
    """
    start = _node_start_line(node)
    end = node.end_lineno
    content = _source_range(lines, start, end)

    return ParsedChunk(
        symbol_name=symbol_name,
        kind=kind,
        start_line=start,
        end_line=end,
        content=content,
        embedded_text=content,   # headers come in pass 5
        token_count=_estimate_tokens(content),
    )
