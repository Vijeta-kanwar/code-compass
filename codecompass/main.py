import logging
import time
import uuid as uuid_lib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from codecompass.api import health, repositories
from codecompass.db import SessionLocal
from codecompass.embedding.client import QuotaExhausted

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexing jobs run inside this process, so a restart kills them mid-flight.
    # They'd otherwise sit in an active status forever, and the partial unique
    # index would refuse every new job for that repository.
    #
    # Blunt but correct while there's exactly one process: nothing can still be
    # legitimately running at startup, so anything active is a corpse.
    #
    # This would be wrong with multiple workers — which is the argument for
    # a real queue.

    with SessionLocal() as session:
        result = session.execute(
            text(
                "UPDATE indexing_job "
                "SET status = 'failed', "
                "    error_message = 'interrupted by process restart', "
                "    finished_at = now() "
                "WHERE status IN "
                "('pending','cloning','parsing','embedding')"
            )
        )

        session.commit()

        if result.rowcount:
            print(f"reaped {result.rowcount} interrupted job(s)")

    yield


# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------

app = FastAPI(
    title="CodeCompass",
    version="0.1.0",
    lifespan=lifespan,
)
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid_lib.uuid4())[:8]
    request.state.request_id = request_id

    start = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    logger.info(
        "%s %s %s %dms rid=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )

    response.headers["X-Request-ID"] = request_id

    return response

# ---------------------------------------------------------
# Routers
# ---------------------------------------------------------

app.include_router(health.router)
app.include_router(repositories.router)


# ---------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    # Client receives only an opaque error ID.
    # Full traceback is written to server logs.
    error_id = str(uuid_lib.uuid4())[:8]

    logger.exception(
        "unhandled error %s on %s %s",
        error_id,
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "error_id": error_id,
        },
    )


# ---------------------------------------------------------
# Expected quota exception
# ---------------------------------------------------------

@app.exception_handler(QuotaExhausted)
async def quota_exhausted(
    request: Request,
    exc: QuotaExhausted,
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "quota_exhausted",
            "detail": str(exc),
        },
    )