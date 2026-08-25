import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import TSVECTOR

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    Computed,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from codecompass.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dimensions

JOB_STATUSES = ("pending", "cloning", "parsing", "embedding", "ready", "failed")
ACTIVE_STATUSES = ("pending", "cloning", "parsing", "embedding")


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Repository(Base):
    __tablename__ = "repository"

    id: Mapped[uuid.UUID] = _pk()
    url: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(String(255))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    # The commit we last successfully indexed. Day 3 compares against this to
    # decide whether a re-index is a no-op.
    last_indexed_commit: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    files: Mapped[list["SourceFile"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class IndexingJob(Base):
    __tablename__ = "indexing_job"

    id: Mapped[uuid.UUID] = _pk()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Counters, not a log. Enough to answer "what did this job do?" from one row.
    files_seen: Mapped[int] = mapped_column(Integer, default=0)
    files_indexed: Mapped[int] = mapped_column(Integer, default=0)
    files_skipped: Mapped[int] = mapped_column(Integer, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(f"status IN {JOB_STATUSES}", name="ck_indexing_job_status"),
        # At most one in-flight job per repo, enforced by the database — two
        # concurrent POSTs can't both win a check-then-insert race.
        Index(
            "ix_one_active_job_per_repo",
            "repository_id",
            unique=True,
            postgresql_where=text(f"status IN {ACTIVE_STATUSES}"),
        ),
    )


class SourceFile(Base):
    __tablename__ = "source_file"

    id: Mapped[uuid.UUID] = _pk()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository.id", ondelete="CASCADE")
    )
    path: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(32))
    # The whole incremental-indexing scheme hangs off this one column.
    content_sha256: Mapped[str] = mapped_column(String(64))
    line_count: Mapped[int] = mapped_column(Integer)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    repository: Mapped[Repository] = relationship(back_populates="files")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("repository_id", "path", name="uq_file_per_repo"),
    )


class Chunk(Base):
    __tablename__ = "chunk"
     
    id: Mapped[uuid.UUID] = _pk()
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_file.id", ondelete="CASCADE")
    )
    # Denormalised on purpose: Day 6 filters by repo *before* the vector scan.
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository.id", ondelete="CASCADE")
    )

    symbol_name: Mapped[str | None] = mapped_column(Text)   # "Session.get"
    kind: Mapped[str] = mapped_column(String(20))           # function|method|class|module
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)

    content: Mapped[str] = mapped_column(Text)              # raw source
    embedded_text: Mapped[str] = mapped_column(Text)        # what the model actually saw
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    content_tsv: Mapped[str | None] = mapped_column(
    TSVECTOR,
    Computed(
        "to_tsvector('english'::regconfig, content)",
        persisted=True,
    ),
     )
    # Null until Day 5 embeds it — which is also how a resumed job finds
    # its unfinished work.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    source_file: Mapped[SourceFile] = relationship(back_populates="chunks")

    __table_args__ = (
        CheckConstraint("end_line >= start_line", name="ck_chunk_line_range"),
        Index("ix_chunk_repository", "repository_id"),
        # Postgres does NOT index foreign keys automatically. Without this,
        # deleting one source_file sequentially scans every chunk to cascade.
        Index("ix_chunk_source_file", "source_file_id"),
    )


class QueryLog(Base):
    __tablename__ = "query_log"

    id: Mapped[uuid.UUID] = _pk()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository.id", ondelete="CASCADE")
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    retrieved_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True))
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )