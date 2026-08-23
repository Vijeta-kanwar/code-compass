from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from codecompass.config import get_settings


api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


def require_api_key(
    x_api_key: str | None = Security(api_key_header),
) -> None:
    """Simple shared-secret gate for expensive API endpoints."""

    expected = get_settings().api_key

    if not expected:
        return

    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )