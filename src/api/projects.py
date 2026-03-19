"""Project endpoints + bullet feedback."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.database import get_db
from src.dependencies import AuthDep, SettingsDep
from src.models import (
    BulletFeedback,
    BulletResponse,
    ProjectCreate,
    ProjectListItem,
    ProjectListResponse,
    ProjectResponse,
)

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(_token: AuthDep, settings: SettingsDep):
    """List all projects with bullet/stale counts and last compile/session timestamps."""
    db = await get_db(settings.context_engine_db)
    try:
        cursor = await db.execute("SELECT id, slug, name, status FROM projects")
        projects = await cursor.fetchall()

        items: list[ProjectListItem] = []
        for p in projects:
            proj_id, slug, name, proj_status = p[0], p[1], p[2], p[3]

            # bullet_count
            cur = await db.execute(
                "SELECT COUNT(*) FROM bullets WHERE project_id = ? AND status IN ('active', 'stale')",
                (proj_id,),
            )
            bullet_count = (await cur.fetchone())[0]

            # stale_count
            cur = await db.execute(
                "SELECT COUNT(*) FROM bullets WHERE project_id = ? AND status = 'stale'",
                (proj_id,),
            )
            stale_count = (await cur.fetchone())[0]

            # last_compiled_at
            cur = await db.execute(
                """SELECT completed_at FROM compile_runs
                   WHERE project_slugs LIKE ? AND completed_at IS NOT NULL
                   ORDER BY completed_at DESC LIMIT 1""",
                (f'%"{slug}"%',),
            )
            row = await cur.fetchone()
            last_compiled_at = row[0] if row else None

            # last_session_at
            cur = await db.execute(
                "SELECT created_at FROM sessions WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (proj_id,),
            )
            row = await cur.fetchone()
            last_session_at = row[0] if row else None

            items.append(ProjectListItem(
                slug=slug,
                name=name,
                status=proj_status,
                bullet_count=bullet_count,
                stale_count=stale_count,
                last_compiled_at=last_compiled_at,
                last_session_at=last_session_at,
            ))

        return ProjectListResponse(projects=items)
    finally:
        await db.close()


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, _token: AuthDep, settings: SettingsDep):
    """Create a new project."""
    db = await get_db(settings.context_engine_db)
    try:
        # Check slug uniqueness
        cur = await db.execute("SELECT id FROM projects WHERE slug = ?", (body.slug,))
        if await cur.fetchone() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project slug '{body.slug}' already exists",
            )

        project_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            """INSERT INTO projects (id, name, slug, notion_page_id, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'active', ?, ?)""",
            (project_id, body.name, body.slug, body.notion_page_id, now, now),
        )
        await db.commit()

        return ProjectResponse(
            id=project_id,
            name=body.name,
            slug=body.slug,
            notion_page_id=body.notion_page_id,
            status="active",
            created_at=now,
            updated_at=now,
        )
    finally:
        await db.close()


@router.get("/projects/{slug}/playbook")
async def get_playbook(
    slug: str,
    _token: AuthDep,
    settings: SettingsDep,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    categories: str | None = Query(None),
):
    """Return compiled playbook for a project."""
    db = await get_db(settings.context_engine_db)
    try:
        # Resolve slug
        cur = await db.execute(
            "SELECT id, name, status FROM projects WHERE slug = ?", (slug,)
        )
        project = await cur.fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")

        proj_id, proj_name, proj_status = project[0], project[1], project[2]

        # Build query
        cat_filter = None
        if categories:
            cat_filter = [c.strip() for c in categories.split(",") if c.strip()]

        if cat_filter:
            placeholders = ",".join("?" for _ in cat_filter)
            cur = await db.execute(
                f"SELECT * FROM bullets WHERE project_id = ? AND status IN ('active', 'stale') AND category IN ({placeholders})",
                [proj_id] + cat_filter,
            )
        else:
            cur = await db.execute(
                "SELECT * FROM bullets WHERE project_id = ? AND status IN ('active', 'stale')",
                (proj_id,),
            )
        rows = await cur.fetchall()
        bullets = [dict(row) for row in rows]

        # Compute staleness_days for each bullet
        now = datetime.now(timezone.utc)
        for b in bullets:
            try:
                verified = datetime.fromisoformat(b["last_verified_at"])
                if verified.tzinfo is None:
                    verified = verified.replace(tzinfo=timezone.utc)
                b["staleness_days"] = (now - verified).days
            except (ValueError, TypeError):
                b["staleness_days"] = 0

        if format == "json":
            return bullets

        # Markdown format — match SPEC.md sections exactly
        return _render_markdown(proj_name, proj_status, bullets, now)
    finally:
        await db.close()


def _render_markdown(
    project_name: str,
    project_status: str,
    bullets: list[dict],
    now: datetime,
) -> str:
    """Render playbook as markdown matching SPEC.md format."""
    compiled_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Group bullets by category
    by_cat: dict[str, list[dict]] = {}
    for b in bullets:
        by_cat.setdefault(b["category"], []).append(b)

    def _bullet_lines(category: str, prefix: str = "- ") -> str:
        items = by_cat.get(category, [])
        if not items:
            return "(none)"
        lines = []
        for b in items:
            ts = b.get("created_at", "")[:10]
            lines.append(f"{prefix}{b['content']} ({ts})")
        return "\n".join(lines)

    def _task_lines() -> str:
        items = by_cat.get("task", [])
        if not items:
            return "(none)"
        lines = []
        for b in items:
            ts = b.get("created_at", "")[:10]
            lines.append(f"- [ ] {b['content']} ({ts})")
        return "\n".join(lines)

    def _next_steps_lines() -> str:
        items = by_cat.get("note", [])
        if not items:
            return "(none)"
        lines = []
        for i, b in enumerate(items, 1):
            lines.append(f"{i}. {b['content']}")
        return "\n".join(lines)

    stale_bullets = [b for b in bullets if b.get("status") == "stale"]
    stale_section = "(none)"
    if stale_bullets:
        lines = []
        for b in stale_bullets:
            days = b.get("staleness_days", 0)
            lines.append(f"- {b['content']} ({days}d stale)")
        stale_section = "\n".join(lines)

    # Determine status line
    status_line = f"{project_status.capitalize()}"

    md = f"""# {project_name} — Project Playbook
*Compiled: {compiled_at}*

## Current Status
{status_line}

## Open Tasks
{_task_lines()}

## Recent Decisions
{_bullet_lines("decision")}

## Active Blockers
{_bullet_lines("blocker")}

## Technical State
{_bullet_lines("tech_state")}

## Stale Items (>48h)
{stale_section}

## Next Steps
{_next_steps_lines()}"""

    return md


# --- Bullet feedback ---

@router.post("/bullets/{bullet_id}/feedback", response_model=BulletResponse)
async def bullet_feedback(
    bullet_id: str,
    body: BulletFeedback,
    _token: AuthDep,
    settings: SettingsDep,
):
    """Submit feedback (helpful/harmful) for a bullet."""
    db = await get_db(settings.context_engine_db)
    try:
        cur = await db.execute("SELECT * FROM bullets WHERE id = ?", (bullet_id,))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Bullet not found")

        bullet = dict(row)

        if body.feedback == "helpful":
            bullet["helpful_count"] += 1
            await db.execute(
                "UPDATE bullets SET helpful_count = ? WHERE id = ?",
                (bullet["helpful_count"], bullet_id),
            )
        else:
            bullet["harmful_count"] += 1
            await db.execute(
                "UPDATE bullets SET harmful_count = ? WHERE id = ?",
                (bullet["harmful_count"], bullet_id),
            )
        await db.commit()

        # Compute staleness_days
        now = datetime.now(timezone.utc)
        try:
            verified = datetime.fromisoformat(bullet["last_verified_at"])
            if verified.tzinfo is None:
                verified = verified.replace(tzinfo=timezone.utc)
            staleness_days = (now - verified).days
        except (ValueError, TypeError):
            staleness_days = 0

        return BulletResponse(
            id=bullet["id"],
            project_id=bullet["project_id"],
            category=bullet["category"],
            content=bullet["content"],
            source=bullet["source"],
            source_id=bullet.get("source_id"),
            status=bullet["status"],
            created_at=bullet["created_at"],
            updated_at=bullet["updated_at"],
            last_verified_at=bullet["last_verified_at"],
            staleness_days=staleness_days,
            helpful_count=bullet["helpful_count"],
            harmful_count=bullet["harmful_count"],
        )
    finally:
        await db.close()
