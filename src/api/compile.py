"""Compile endpoints — trigger compile as BackgroundTask, check status."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from src.compiler import run_compile
from src.database import get_db
from src.dependencies import AuthDep, SettingsDep
from src.models import CompileRequest, CompileRunResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["compile"])


@router.post("/compile", status_code=status.HTTP_202_ACCEPTED)
async def trigger_compile(
    background_tasks: BackgroundTasks,
    _token: AuthDep,
    settings: SettingsDep,
    body: CompileRequest | None = None,
):
    """Start a compile run as a background task. Returns 202 immediately."""
    slug = body.project_slug if body else None

    # Determine which projects will be compiled
    db = await get_db(settings.context_engine_db)
    try:
        if slug:
            cur = await db.execute(
                "SELECT slug FROM projects WHERE slug = ? AND status = 'active'", (slug,)
            )
            rows = await cur.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")
            project_slugs = [slug]
        else:
            cur = await db.execute("SELECT slug FROM projects WHERE status = 'active'")
            rows = await cur.fetchall()
            project_slugs = [r[0] for r in rows]
    finally:
        await db.close()

    # Schedule background compile
    background_tasks.add_task(run_compile, project_slug=slug, settings=settings)

    return {
        "compile_run_id": "pending",
        "status": "started",
        "projects": project_slugs,
    }


@router.get("/compile/{run_id}", response_model=CompileRunResponse)
async def get_compile_run(run_id: str, _token: AuthDep, settings: SettingsDep):
    """Return compile run status/stats."""
    db = await get_db(settings.context_engine_db)
    try:
        cur = await db.execute("SELECT * FROM compile_runs WHERE id = ?", (run_id,))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Compile run not found")

        record = dict(row)
        return CompileRunResponse(
            id=record["id"],
            started_at=record["started_at"],
            completed_at=record.get("completed_at"),
            project_slugs=json.loads(record.get("project_slugs", "[]")),
            bullets_added=record.get("bullets_added", 0),
            bullets_updated=record.get("bullets_updated", 0),
            bullets_archived=record.get("bullets_archived", 0),
            llm_provider=record.get("llm_provider"),
            llm_model=record.get("llm_model"),
            error=record.get("error"),
        )
    finally:
        await db.close()
