import shutil
import subprocess
from pathlib import Path

from codecompass.config import get_settings


class CloneFailed(RuntimeError):
    pass


def shallow_clone(url: str, dest: Path) -> str:
    """Clone at depth 1 and return the HEAD commit SHA."""
    settings = get_settings()
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # A list, never a string with shell=True — the URL is user input.
    # --no-recurse-submodules stops the repo from pulling in code we never vetted.
    cmd = [
        "git", "clone", "--depth", "1", "--single-branch",
        "--no-recurse-submodules", url, str(dest),
    ]
    try:
        subprocess.run(
            cmd, check=True, capture_output=True, text=True,
            timeout=settings.clone_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        raise CloneFailed(f"Clone exceeded {settings.clone_timeout_seconds}s.")
    except subprocess.CalledProcessError as exc:
        # git puts the useful part on stderr; the last line is usually enough.
        detail = (exc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        raise CloneFailed(f"git clone failed: {detail[0]}")

    size_mb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / 1e6
    if size_mb > settings.max_repo_mb:
        shutil.rmtree(dest, ignore_errors=True)
        raise CloneFailed(f"Repository is {size_mb:.0f}MB, limit is {settings.max_repo_mb}MB.")

    head = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return head.stdout.strip()