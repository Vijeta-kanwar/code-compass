import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_CHUNK_TOKENS = 1500


@dataclass(frozen=True)
class ParsedChunk:
    symbol_name: str | None
    kind: str
    start_line: int
    end_line: int
    content: str
    embedded_text: str
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

    lines = content.splitlines()

    if not lines:
        return []

    chunks: list[ParsedChunk] = []

    # Header used by module-level chunks.
    module_header = _context_header(path, None, None)

    first_def = next(
        (
            _node_start_line(n)
            for n in tree.body
            if isinstance(
                n,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            )
        ),
        None,
    )

    # Files containing no classes/functions are still useful.
    # Keep the whole file as a module chunk.
    if first_def is None:
        content_slice = _source_range(lines, 1, len(lines))

        if content_slice.strip():
            chunks.append(
                ParsedChunk(
                    symbol_name=None,
                    kind="module",
                    start_line=1,
                    end_line=len(lines),
                    content=content_slice,
                    embedded_text=module_header + content_slice,
                    # token_count is for the content sent to the LLM,
                    # not the embedding-only context header.
                    token_count=_estimate_tokens(content_slice),
                )
            )

        return chunks

    # Module preamble: imports, constants, docstring, etc.
    end_line = first_def - 1

    if end_line >= 1:
        content_slice = _source_range(lines, 1, end_line)

        if content_slice.strip():
            chunks.append(
                ParsedChunk(
                    symbol_name=None,
                    kind="module",
                    start_line=1,
                    end_line=end_line,
                    content=content_slice,
                    embedded_text=module_header + content_slice,
                    token_count=_estimate_tokens(content_slice),
                )
            )

    # Top-level functions and classes.
    for node in tree.body:

        # FunctionDef and AsyncFunctionDef are siblings.
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            chunks.append(
                _build_def_chunk(
                    node=node,
                    lines=lines,
                    symbol_name=node.name,
                    kind="function",
                    header=module_header,
                )
            )

        elif isinstance(node, ast.ClassDef):

            # Only direct methods of this class.
            # We intentionally don't use ast.walk(), so nested functions
            # remain inside their parent function's source range.
            methods = [
                child
                for child in node.body
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                )
            ]

            class_doc = ast.get_docstring(node)

            # Class chunk stops immediately before the first method.
            class_start = _node_start_line(node)

            class_end = (
                _node_start_line(methods[0]) - 1
                if methods
                else node.end_lineno
            )

            if class_end >= class_start:
                class_content = _source_range(
                    lines,
                    class_start,
                    class_end,
                )

                if class_content.strip():
                    class_header = _context_header(
                        path,
                        node.name,
                        class_doc,
                    )

                    chunks.append(
                        ParsedChunk(
                            symbol_name=node.name,
                            kind="class",
                            start_line=class_start,
                            end_line=class_end,
                            content=class_content,
                            embedded_text=(
                                class_header + class_content
                            ),
                            token_count=_estimate_tokens(
                                class_content
                            ),
                        )
                    )

            # Individual methods.
            method_header = _context_header(
                path,
                node.name,
                class_doc,
            )

            for method in methods:
                chunks.append(
                    _build_def_chunk(
                        node=method,
                        lines=lines,
                        symbol_name=f"{node.name}.{method.name}",
                        kind="method",
                        header=method_header,
                    )
                )

    # Stable source order.
    return sorted(
        chunks,
        key=lambda c: c.start_line,
    )


def _estimate_tokens(text: str) -> int:
    """
    ~4 chars per token.

    Deliberately a heuristic: calling the real tokenizer per chunk
    would burn free-tier quota needed for actual embedding.
    """
    return len(text) // 4


def _source_range(
    lines: list[str],
    start: int,
    end: int,
) -> str:
    """
    Slice by 1-based inclusive line numbers,
    the way AST reports them.
    """
    return "\n".join(lines[start - 1:end])


def _node_start_line(node: ast.AST) -> int:
    """
    First line of the node including its decorators.
    """
    line = node.lineno

    decorators = getattr(node, "decorator_list", [])

    if decorators:
        line = min(
            line,
            *(d.lineno for d in decorators),
        )

    return line


def _build_def_chunk(
    node: ast.AST,
    lines: list[str],
    symbol_name: str,
    kind: str,
    header: str,
) -> ParsedChunk:
    """
    Turn one def/async def node into a chunk.

    Shared by top-level functions and class methods.
    """
    start = _node_start_line(node)
    end = node.end_lineno

    content = _source_range(
        lines,
        start,
        end,
    )

    embedded_text = header + content

    return ParsedChunk(
        symbol_name=symbol_name,
        kind=kind,
        start_line=start,
        end_line=end,
        content=content,
        embedded_text=embedded_text,
        # Count only content because that is what the LLM receives.
        token_count=_estimate_tokens(content),
    )


def _context_header(
    path: str,
    class_name: str | None,
    class_doc: str | None,
) -> str:
    lines = [f"File: {path}"]

    if class_name:
        doc = (class_doc or "").strip().splitlines()

        lines.append(
            f"Class: {class_name}"
            + (f" — {doc[0]}" if doc else "")
        )

    return "\n".join(lines) + "\n\n"