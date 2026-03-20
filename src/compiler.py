"""ACE-inspired compile loop — harvest, compile via LLM, apply deltas, staleness scan."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import jinja2

from src.config import Settings
from src.database import get_db
from src.harvester import harvest_all
from src.llm import LLMClient
from src.models import CompileDelta

logger = logging.getLogger(__name__)

# Module-level lock to prevent concurrent compiles (Review Fix 1)
_compile_lock = asyncio.Lock()

# Load Jinja2 template once
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=False,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _staleness_threshold(category: str, settings: Settings) -> int:
    """Return staleness threshold in hours for a bullet category."""
    thresholds = {
        "task": settings.staleness_hours_task,
        "decision": settings.staleness_hours_decision,
        "blocker": settings.staleness_hours_blocker,
        "tech_state": settings.staleness_hours_tech_state,
        "note": settings.staleness_hours_note,
    }
    return thresholds.get(category, settings.staleness_hours_note)


async def _get_last_compile_time(db: aiosqlite.Connection, project_slug: str) -> str | None:
    """Get the completed_at of the most recent SUCCESSFUL compile for a project.
    
    Only considers compiles where error IS NULL — failed compiles must not
    advance the 'since' window or unprocessed sessions get permanently skipped.
    """
    cursor = await db.execute(
        """SELECT completed_at FROM compile_runs
           WHERE project_slugs LIKE ? AND completed_at IS NOT NULL AND error IS NULL
           ORDER BY completed_at DESC LIMIT 1""",
        (f'%"{project_slug}"%',),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def _get_active_bullets(db: aiosqlite.Connection, project_id: str) -> list[dict]:
    """Load all active bullets for a project."""
    cursor = await db.execute(
        "SELECT * FROM bullets WHERE project_id = ? AND status = 'active'",
        (project_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def _get_local_sessions(
    db: aiosqlite.Connection, project_id: str, since: str | None,
) -> list[dict]:
    """Get session handovers from the local sessions table since last compile."""
    if since:
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE project_id = ? AND created_at > ?",
            (project_id, since),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE project_id = ?",
            (project_id,),
        )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


def _sessions_to_harvested_json(sessions: list[dict]) -> list[dict]:
    """Convert local sessions into harvested-item-like dicts for the LLM prompt."""
    items = []
    for s in sessions:
        parts = [s.get("summary", "")]
        for field in ("decisions", "open_items", "tech_changes", "next_steps"):
            vals = json.loads(s.get(field, "[]"))
            if vals:
                parts.append(f"{field}: {', '.join(vals)}")
        items.append({
            "source": "session_handover",
            "source_id": s["id"],
            "content": " | ".join(parts),
            "category": "note",
            "timestamp": s["created_at"],
        })
    return items


async def _apply_deltas(
    db: aiosqlite.Connection,
    project_id: str,
    delta: CompileDelta,
) -> tuple[int, int, int]:
    """Apply CompileDelta to the database. Returns (added, updated, archived) counts."""
    now = _now()
    added = 0
    updated = 0
    archived = 0

    for bullet in delta.add:
        bullet_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO bullets
               (id, project_id, category, content, source, source_id, status,
                created_at, updated_at, last_verified_at, helpful_count, harmful_count)
               VALUES (?, ?, ?, ?, ?, NULL, 'active', ?, ?, ?, 0, 0)""",
            (bullet_id, project_id, bullet.category, bullet.content,
             bullet.source, now, now, now),
        )
        added += 1

    for upd in delta.update:
        cursor = await db.execute(
            "SELECT id FROM bullets WHERE id = ? AND project_id = ?",
            (upd.bullet_id, project_id),
        )
        if await cursor.fetchone() is None:
            logger.warning("Skipping update for non-existent bullet_id: %s", upd.bullet_id)
            continue
        await db.execute(
            """UPDATE bullets SET content = ?, updated_at = ?, last_verified_at = ?
               WHERE id = ?""",
            (upd.content, now, now, upd.bullet_id),
        )
        updated += 1

    for arch in delta.archive:
        cursor = await db.execute(
            "SELECT id FROM bullets WHERE id = ? AND project_id = ?",
            (arch.bullet_id, project_id),
        )
        if await cursor.fetchone() is None:
            logger.warning("Skipping archive for non-existent bullet_id: %s", arch.bullet_id)
            continue
        await db.execute(
            "UPDATE bullets SET status = 'archived', updated_at = ? WHERE id = ?",
            (now, arch.bullet_id),
        )
        archived += 1

    return added, updated, archived


async def _staleness_scan(db: aiosqlite.Connection, project_id: str, settings: Settings) -> None:
    """Check active bullets against per-category staleness thresholds."""
    now = datetime.now(timezone.utc)
    cursor = await db.execute(
        "SELECT id, category, last_verified_at FROM bullets WHERE project_id = ? AND status = 'active'",
        (project_id,),
    )
    rows = await cursor.fetchall()
    for row in rows:
        bullet_id = row[0]
        category = row[1]
        last_verified = row[2]
        threshold_hours = _staleness_threshold(category, settings)
        try:
            verified_dt = datetime.fromisoformat(last_verified)
            if verified_dt.tzinfo is None:
                verified_dt = verified_dt.replace(tzinfo=timezone.utc)
            age_hours = (now - verified_dt).total_seconds() / 3600
        except (ValueError, TypeError):
            age_hours = float("inf")

        if threshold_hours == 0 or age_hours > threshold_hours:
            await db.execute(
                "UPDATE bullets SET status = 'stale' WHERE id = ?",
                (bullet_id,),
            )


async def run_compile(
    project_slug: str | None = None,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
) -> dict:
    """Main compile entry point. Runs as BackgroundTask inside FastAPI."""
    async with _compile_lock:
        return await _run_compile_inner(project_slug, settings, llm_client)


async def _run_compile_inner(
    project_slug: str | None,
    settings: Settings | None,
    llm_client: LLMClient | None,
) -> dict:
    settings = settings or Settings()
    llm = llm_client or LLMClient(settings)

    run_id = str(uuid.uuid4())
    started_at = _now()
    total_added = 0
    total_updated = 0
    total_archived = 0
    compiled_slugs: list[str] = []
    error: str | None = None

    db = await get_db(settings.context_engine_db)
    try:
        if project_slug:
            cursor = await db.execute(
                "SELECT id, slug, name FROM projects WHERE slug = ? AND status = 'active'",
                (project_slug,),
            )
        else:
            cursor = await db.execute(
                "SELECT id, slug, name FROM projects WHERE status = 'active'"
            )
        projects = await cursor.fetchall()

        if not projects:
            logger.warning("No active projects found to compile")

        for project in projects:
            proj_id = project[0]
            proj_slug = project[1]
            proj_name = project[2]

            try:
                last_compile = await _get_last_compile_time(db, proj_slug)
                logger.info("Compiling %s (since=%s)", proj_slug, last_compile)

                harvested = await harvest_all(proj_slug, since=last_compile)
                local_sessions = await _get_local_sessions(db, proj_id, last_compile)
                local_harvested = _sessions_to_harvested_json(local_sessions)
                current_bullets = await _get_active_bullets(db, proj_id)
                harvested_dicts = [item.model_dump() for item in harvested] + local_harvested

                logger.info(
                    "%s: %d harvested, %d local sessions, %d current bullets",
                    proj_slug, len(harvested), len(local_sessions), len(current_bullets),
                )

                if not harvested_dicts and not current_bullets:
                    logger.info("No data for %s, skipping", proj_slug)
                    compiled_slugs.append(proj_slug)
                    await _staleness_scan(db, proj_id, settings)
                    continue

                if not harvested_dicts:
                    logger.info("No new data for %s, skipping LLM", proj_slug)
                    compiled_slugs.append(proj_slug)
                    await _staleness_scan(db, proj_id, settings)
                    continue

                template = _jinja_env.get_template("compile_prompt.md")
                prompt = template.render(
                    project_name=proj_name,
                    current_bullets_json=json.dumps(current_bullets, indent=2),
                    harvested_data_json=json.dumps(harvested_dicts, indent=2),
                )

                delta = await llm.compile(prompt)
                if delta is None:
                    logger.warning("LLM failed for %s, skipping", proj_slug)
                    error = f"{proj_slug}: LLM returned None"
                    compiled_slugs.append(proj_slug)
                    await _staleness_scan(db, proj_id, settings)
                    continue

                added, updated, archived = await _apply_deltas(db, proj_id, delta)
                total_added += added
                total_updated += updated
                total_archived += archived
                await _staleness_scan(db, proj_id, settings)
                compiled_slugs.append(proj_slug)
                logger.info("Compiled %s: +%d ~%d -%d", proj_slug, added, updated, archived)

            except Exception as exc:
                logger.error("Compile failed for %s: %s", proj_slug, exc)
                error = f"{proj_slug}: {exc}"

        await db.commit()

        completed_at = _now()
        await db.execute(
            """INSERT INTO compile_runs
               (id, started_at, completed_at, project_slugs,
                bullets_added, bullets_updated, bullets_archived,
                llm_provider, llm_model, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, started_at, completed_at,
                json.dumps(compiled_slugs),
                total_added, total_updated, total_archived,
                "openrouter", "deepseek/deepseek-chat", error,
            ),
        )
        await db.commit()

        return {
            "id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "project_slugs": compiled_slugs,
            "bullets_added": total_added,
            "bullets_updated": total_updated,
            "bullets_archived": total_archived,
            "llm_provider": "openrouter",
            "llm_model": "deepseek/deepseek-chat",
            "error": error,
        }

    except Exception as exc:
        logger.error("Compile run failed: %s", exc)
        try:
            await db.execute(
                """INSERT INTO compile_runs
                   (id, started_at, completed_at, project_slugs,
                    bullets_added, bullets_updated, bullets_archived,
                    llm_provider, llm_model, error)
                   VALUES (?, ?, NULL, ?, 0, 0, 0, NULL, NULL, ?)""",
                (run_id, started_at, json.dumps(compiled_slugs), str(exc)),
            )
            await db.commit()
        except Exception:
            pass
        return {
            "id": run_id, "started_at": started_at, "completed_at": None,
            "project_slugs": compiled_slugs, "bullets_added": 0,
            "bullets_updated": 0, "bullets_archived": 0,
            "llm_provider": None, "llm_model": None, "error": str(exc),
        }
    finally:
        await db.close()
