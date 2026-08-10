import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_CHUNK_TOKENS = 1500


@dataclass(frozen=True)
class ParsedChunk:
    symbol_name: str | None   # "Session.get", "get_encoding", None for module
    kind: str                 # module | class | function | method
    start_line: int           # 1-based, inclusive
    end_line: int             # 1-based, inclusive
    content: str              # raw source slice — no header, ever
    embedded_text: str        # context header + content
    token_count: int


def chunk_python_file(content: str, path: str) -> list[ParsedChunk]:
    """Split one Python file into retrievable units.

    Returns [] rather than raising on unparseable input — one bad file must
    never take down an indexing job.
    """
    # TODO
    return []


def _estimate_tokens(text: str) -> int:
    # ~4 chars per token. Deliberately a heuristic: calling the real tokenizer
    # per chunk would burn free-tier quota we need for actual embedding.
    return len(text) // 4


def _source_range(lines: list[str], start: int, end: int) -> str:
    """Slice by 1-based inclusive line numbers, the way ast reports them."""
    # TODO
    ...


def _node_start_line(node: ast.AST) -> int:
    """First line of the node *including* its decorators."""
    # TODO
    ...