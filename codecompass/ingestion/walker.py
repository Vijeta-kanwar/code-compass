import hashlib
from dataclasses import dataclass
from pathlib import Path

from codecompass.config import get_settings

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".tox", "site-packages",
}


@dataclass(frozen=True)
class WalkedFile:
    path: str          # relative to the repo root — what we show the user
    content: str
    sha256: str
    line_count: int


def walk_python_files(root: Path):
    """Yield the Python files worth indexing, with a hash of each one's content."""
    settings = get_settings()

    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.stat().st_size > settings.max_file_bytes:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            # Not all .py files are valid UTF-8. Skipping beats crashing a job.
            continue

        yield WalkedFile(
            path=str(path.relative_to(root)),
            content=content,
            # Hash the content, not the mtime — a fresh clone has fresh mtimes
            # on every file, which would defeat incremental indexing entirely.
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            line_count=content.count("\n") + 1,
        )