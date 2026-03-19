"""POST /sessions — structured session handover submission."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from src.database import get_db
from src.dependencies import AuthDep, SettingsDep
from src.models import SessionCreate, SessionResponse

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionCreate, _token: AuthDep, settings: SettingsDep):
    """Submit a structured session handover."""
    db = await get_db(settings.context_engine_db)
    try:
        # Resolve project_slug → project_id
        cursor = await db.execute(
            "SELECT id FROM projects WHERE slug = ?", (body.project_slug,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{body.project_slug}' not found",
            )
        project_id = row[0]

        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            """INSERT INTO sessions
               (id, project_id, summary, decisions, open_items, tech_changes, next_steps, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                project_id,
                body.summary,
                json.dumps(body.decisions),
                json.dumps(body.open_items),
                json.dumps(body.tech_changes),
                json.dumps(body.next_steps),
                now,
            ),
        )
        await db.commit()

        return SessionResponse(
            id=session_id,
            project_slug=body.project_slug,
            created_at=now,
        )
    finally:
        await db.close()
