import pytest

from codecompass.config import get_settings
from codecompass.services.repo_url import InvalidRepositoryUrl, normalize


def test_normalize_valid_https_url(monkeypatch):
    monkeypatch.setenv("ALLOWED_GIT_HOSTS", "github.com")
    get_settings.cache_clear()

    assert normalize("https://github.com/owner/repo") == (
        "https://github.com/owner/repo",
        "repo",
    )


def test_normalize_removes_git_suffix_query_and_fragment(monkeypatch):
    monkeypatch.setenv("ALLOWED_GIT_HOSTS", "github.com")
    get_settings.cache_clear()

    assert normalize("https://github.com/owner/repo.git?foo=bar#readme") == (
        "https://github.com/owner/repo",
        "repo",
    )


@pytest.mark.parametrize(
    ("url", "message"),
    [
        (
            "http://github.com/owner/repo",
            "Only https:// URLs are accepted.",
        ),
        (
            "https://user:password@github.com/owner/repo",
            "URLs must not contain credentials.",
        ),
        (
            "https://gitlab.com/owner/repo",
            "Host 'gitlab.com' is not allowed.",
        ),
        (
            "https://github.com/owner",
            "Expected a path of the form /owner/repo.",
        ),
        (
            "https://github.com/owner/repo/extra",
            "Expected a path of the form /owner/repo.",
        ),
    ],
)
def test_normalize_rejects_invalid_urls(monkeypatch, url, message):
    monkeypatch.setenv("ALLOWED_GIT_HOSTS", "github.com")
    get_settings.cache_clear()

    with pytest.raises(InvalidRepositoryUrl, match=message):
        normalize(url)
