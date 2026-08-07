from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from codecompass.config import get_settings

_engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,   # pooled connections go stale; test one before handing it out
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """One session per request — committed on success, rolled back on error, always closed."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()