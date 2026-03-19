"""Shared FastAPI dependencies — auth, settings."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import Settings

_settings = Settings()
_bearer = HTTPBearer()


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """Validate bearer token against config. Returns the token on success."""
    if credentials.credentials != _settings.context_engine_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )
    return credentials.credentials


def get_settings() -> Settings:
    return _settings


AuthDep = Annotated[str, Depends(verify_token)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
