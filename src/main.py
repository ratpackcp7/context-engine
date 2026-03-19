"""FastAPI app — lifespan, router includes, health endpoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import Settings
from src.database import init_db
from src.models import HealthResponse

logger = logging.getLogger(__name__)

_settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise database."""
    logger.info("Initialising database at %s", _settings.context_engine_db)
    await init_db(_settings.context_engine_db)
    yield


app = FastAPI(title="Context Engine", version="1.0.0", lifespan=lifespan)


# --- Health (no auth) ---

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


# --- Register routers ---

from src.api.sessions import router as sessions_router  # noqa: E402
from src.api.projects import router as projects_router  # noqa: E402
from src.api.compile import router as compile_router  # noqa: E402
from src.api.digest import router as digest_router  # noqa: E402

app.include_router(sessions_router)
app.include_router(projects_router)
app.include_router(compile_router)
app.include_router(digest_router)
