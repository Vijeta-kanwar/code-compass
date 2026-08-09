from urllib.parse import urlparse

from codecompass.config import get_settings


class InvalidRepositoryUrl(ValueError):
    """Raised for anything we refuse to clone. The message is user-facing."""


def normalize(raw: str) -> tuple[str, str]:
    """Validate a git URL and return (canonical_url, repo_name).

    Everything here is a rejection rule, not a convenience. This function is the
    only thing standing between a user-supplied string and a shell-out to git.
    """
    settings = get_settings()
    parsed = urlparse(raw.strip())

    if parsed.scheme != "https":
        raise InvalidRepositoryUrl("Only https:// URLs are accepted.")

    # Credentials in the URL would end up in our logs and in the job row.
    if parsed.username or parsed.password:
        raise InvalidRepositoryUrl("URLs must not contain credentials.")

    host = (parsed.hostname or "").lower()
    if host not in settings.git_host_allowlist:
        raise InvalidRepositoryUrl(f"Host '{host}' is not allowed.")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2:
        raise InvalidRepositoryUrl("Expected a path of the form /owner/repo.")

    owner, repo = parts[0], parts[1].removesuffix(".git")
    # Rebuild rather than pass the input through — drops query strings,
    # fragments, and any path trickery that survived the checks above.
    return f"https://{host}/{owner}/{repo}", repo