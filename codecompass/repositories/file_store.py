import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from codecompass.models import Chunk, SourceFile


class FileStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def hashes_for_repository(self, repository_id: uuid.UUID) -> dict[str, str]:
        """path -> content_sha256 for everything currently indexed.

        Loaded once per job rather than queried per file: one round trip beats
        several thousand.
        """
        rows = self._session.execute(
            select(SourceFile.path, SourceFile.content_sha256)
            .where(SourceFile.repository_id == repository_id)
        )
        return {path: sha for path, sha in rows}

    def get_by_path(self, repository_id: uuid.UUID, path: str) -> SourceFile | None:
        return self._session.scalar(
            select(SourceFile).where(
                SourceFile.repository_id == repository_id, SourceFile.path == path
            )
        )

    def upsert(
        self, *, repository_id: uuid.UUID, path: str, language: str,
        sha256: str, line_count: int,
    ) -> SourceFile:
        existing = self.get_by_path(repository_id, path)
        if existing:
            existing.line_count = line_count
            # Note what is NOT set here: content_sha256. The caller writes that
            # last, once the chunks it vouches for are actually in the table.
            self._session.flush()
            return existing

        file = SourceFile(
            repository_id=repository_id, path=path, language=language,
            content_sha256="", line_count=line_count,
        )
        self._session.add(file)
        self._session.flush()
        return file

    def delete_chunks(self, source_file_id: uuid.UUID) -> None:
        self._session.execute(delete(Chunk).where(Chunk.source_file_id == source_file_id))

    def delete_files_not_in(self, repository_id: uuid.UUID, keep_paths: set[str]) -> int:
        """Drop files that vanished upstream. Chunks go with them via cascade."""
        result = self._session.execute(
            delete(SourceFile).where(
                SourceFile.repository_id == repository_id,
                SourceFile.path.notin_(keep_paths) if keep_paths else True,
            )
        )
        return result.rowcount or 0