from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from codecompass.db import get_session

router = APIRouter(tags=["ops"])


@router.get("/healthz")
def liveness() -> dict[str, str]:
    # Touches nothing, deliberately. A failing database should never be the
    # reason an orchestrator kills and restarts this container.
    return {"status": "ok"}


@router.get("/readyz")
def readiness(
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ok", "database": "ok"}