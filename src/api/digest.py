"""Digest endpoint — GET /digest/latest."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.database import get_db
from src.dependencies import AuthDep, SettingsDep
from src.models import DigestResponse

router = APIRouter(tags=["digest"])


@router.get("/digest/latest", response_model=DigestResponse)
async def get_latest_digest(_token: AuthDep, settings: SettingsDep):
    """Return the most recent digest record."""
    db = await get_db(settings.context_engine_db)
    try:
        cur = await db.execute(
            "SELECT * FROM digests ORDER BY generated_at DESC LIMIT 1"
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="No digests found")

        record = dict(row)
        return DigestResponse(
            id=record["id"],
            generated_at=record["generated_at"],
            stale_count=record["stale_count"],
            summary_text=record["summary_text"],
            sent_telegram=bool(record["sent_telegram"]),
            sent_email=bool(record["sent_email"]),
        )
    finally:
        await db.close()
