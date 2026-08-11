from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from codecompass.api import health, repositories
from codecompass.db import SessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexing jobs run inside this process, so a restart kills them mid-flight.
    # They'd otherwise sit in an active status forever, and the partial unique
    # index would refuse every new job for that repository.
    #
    # Blunt but correct while there's exactly one process: nothing can still be
    # legitimately running at startup, so anything active is a corpse. This would
    # be wrong with multiple workers — which is the argument for a real queue.
    with SessionLocal() as session:
        result = session.execute(
            text(
                "UPDATE indexing_job "
                "SET status = 'failed', "
                "    error_message = 'interrupted by process restart', "
                "    finished_at = now() "
                "WHERE status IN ('pending','cloning','parsing','embedding')"
            )
        )
        session.commit()
        if result.rowcount:
            print(f"reaped {result.rowcount} interrupted job(s)")

    yield


app = FastAPI(title="CodeCompass", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(repositories.router)