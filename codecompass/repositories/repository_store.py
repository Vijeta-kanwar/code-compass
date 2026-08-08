import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from codecompass.models import Repository


class RepositoryStore:
    """All SQL touching the repository table. No HTTP objects, no business rules."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, repository_id: uuid.UUID) -> Repository | None:
        return self._session.get(Repository, repository_id)

    def get_by_url(self, url: str) -> Repository | None:
        return self._session.scalar(select(Repository).where(Repository.url == url))

    def create(self, *, url: str, name: str, default_branch: str = "main") -> Repository:
        repo = Repository(url=url, name=name, default_branch=default_branch)
        self._session.add(repo)
        # flush, not commit — the caller owns the transaction boundary. Day 3
        # needs a repo and its first job to land together or not at all.
        self._session.flush()
        return repo