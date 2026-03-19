"""Tests for the ACE-inspired compile loop."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.compiler import run_compile, _staleness_scan, _apply_deltas
from src.config import Settings
from src.database import init_db, get_db
from src.models import CompileDelta, BulletAdd, BulletUpdate, BulletArchive


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _past(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


@pytest_asyncio.fixture
async def db_path(tmp_path):
    """Create a temporary SQLite database."""
    path = str(tmp_path / "test.db")
    await init_db(path)
    return path


@pytest_asyncio.fixture
async def settings(db_path):
    """Settings pointing to temp DB."""
    return Settings(
        context_engine_db=db_path,
        gemini_api_key="",
        staleness_hours_task=48,
        staleness_hours_decision=168,
        staleness_hours_blocker=0,
        staleness_hours_tech_state=168,
        staleness_hours_note=336,
    )


@pytest_asyncio.fixture
async def project_id(db_path):
    """Insert a test project and return its ID."""
    pid = str(uuid.uuid4())
    now = _now()
    db = await get_db(db_path)
    await db.execute(
        "INSERT INTO projects (id, name, slug, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (pid, "Test Project", "test-project", "active", now, now),
    )
    await db.commit()
    await db.close()
    return pid


async def _insert_bullet(db_path, project_id, category="task", content="Test bullet",
                          status="active", last_verified_at=None, bullet_id=None):
    """Helper to insert a bullet."""
    bid = bullet_id or str(uuid.uuid4())
    now = _now()
    lv = last_verified_at or now
    db = await get_db(db_path)
    await db.execute(
        """INSERT INTO bullets
           (id, project_id, category, content, source, source_id, status,
            created_at, updated_at, last_verified_at, helpful_count, harmful_count)
           VALUES (?, ?, ?, ?, 'manual', NULL, ?, ?, ?, ?, 0, 0)""",
        (bid, project_id, category, content, status, now, now, lv),
    )
    await db.commit()
    await db.close()
    return bid


class TestApplyDeltas:
    """Test delta application to database."""

    @pytest.mark.asyncio
    async def test_add_bullets(self, db_path, project_id):
        delta = CompileDelta(
            add=[
                BulletAdd(category="task", content="New task from LLM", source="notion_todo"),
                BulletAdd(category="decision", content="Use Redis", source="session_handover"),
            ]
        )
        db = await get_db(db_path)
        added, updated, archived = await _apply_deltas(db, project_id, delta)
        await db.commit()

        assert added == 2
        assert updated == 0
        assert archived == 0

        cursor = await db.execute("SELECT COUNT(*) FROM bullets WHERE project_id = ?", (project_id,))
        count = (await cursor.fetchone())[0]
        assert count == 2
        await db.close()

    @pytest.mark.asyncio
    async def test_update_bullet(self, db_path, project_id):
        bid = await _insert_bullet(db_path, project_id, content="Old content")
        delta = CompileDelta(
            update=[BulletUpdate(bullet_id=bid, content="Updated content")]
        )
        db = await get_db(db_path)
        added, updated, archived = await _apply_deltas(db, project_id, delta)
        await db.commit()

        assert updated == 1
        cursor = await db.execute("SELECT content FROM bullets WHERE id = ?", (bid,))
        row = await cursor.fetchone()
        assert row[0] == "Updated content"
        await db.close()

    @pytest.mark.asyncio
    async def test_archive_bullet(self, db_path, project_id):
        bid = await _insert_bullet(db_path, project_id)
        delta = CompileDelta(
            archive=[BulletArchive(bullet_id=bid, reason="Task completed")]
        )
        db = await get_db(db_path)
        added, updated, archived = await _apply_deltas(db, project_id, delta)
        await db.commit()

        assert archived == 1
        cursor = await db.execute("SELECT status FROM bullets WHERE id = ?", (bid,))
        row = await cursor.fetchone()
        assert row[0] == "archived"
        await db.close()

    @pytest.mark.asyncio
    async def test_invalid_bullet_id_skipped(self, db_path, project_id):
        """Invalid bullet_id in update/archive should be skipped, not crash."""
        delta = CompileDelta(
            update=[BulletUpdate(bullet_id="nonexistent-id", content="Won't apply")],
            archive=[BulletArchive(bullet_id="also-fake", reason="Doesn't exist")],
        )
        db = await get_db(db_path)
        added, updated, archived = await _apply_deltas(db, project_id, delta)
        await db.commit()

        assert updated == 0
        assert archived == 0
        await db.close()


class TestStalenessScan:
    """Test per-category staleness threshold scanning."""

    @pytest.mark.asyncio
    async def test_stale_task(self, db_path, project_id, settings):
        """Task older than 48h threshold should be marked stale."""
        bid = await _insert_bullet(
            db_path, project_id, category="task",
            last_verified_at=_past(50),
        )
        db = await get_db(db_path)
        await _staleness_scan(db, project_id, settings)
        await db.commit()

        cursor = await db.execute("SELECT status FROM bullets WHERE id = ?", (bid,))
        row = await cursor.fetchone()
        assert row[0] == "stale"
        await db.close()

    @pytest.mark.asyncio
    async def test_fresh_task_not_stale(self, db_path, project_id, settings):
        """Task within 48h threshold should stay active."""
        bid = await _insert_bullet(
            db_path, project_id, category="task",
            last_verified_at=_past(10),
        )
        db = await get_db(db_path)
        await _staleness_scan(db, project_id, settings)
        await db.commit()

        cursor = await db.execute("SELECT status FROM bullets WHERE id = ?", (bid,))
        row = await cursor.fetchone()
        assert row[0] == "active"
        await db.close()

    @pytest.mark.asyncio
    async def test_blocker_always_stale(self, db_path, project_id, settings):
        """Blockers have threshold=0, so they are always flagged as stale."""
        bid = await _insert_bullet(
            db_path, project_id, category="blocker",
            last_verified_at=_now(),
        )
        db = await get_db(db_path)
        await _staleness_scan(db, project_id, settings)
        await db.commit()

        cursor = await db.execute("SELECT status FROM bullets WHERE id = ?", (bid,))
        row = await cursor.fetchone()
        assert row[0] == "stale"
        await db.close()

    @pytest.mark.asyncio
    async def test_decision_staleness(self, db_path, project_id, settings):
        """Decision older than 168h should be stale."""
        bid = await _insert_bullet(
            db_path, project_id, category="decision",
            last_verified_at=_past(200),
        )
        db = await get_db(db_path)
        await _staleness_scan(db, project_id, settings)
        await db.commit()

        cursor = await db.execute("SELECT status FROM bullets WHERE id = ?", (bid,))
        row = await cursor.fetchone()
        assert row[0] == "stale"
        await db.close()


class TestRunCompile:
    """Integration tests for run_compile with mocked LLM and harvesters."""

    @pytest.mark.asyncio
    async def test_compile_with_valid_delta(self, db_path, project_id, settings):
        """Mock LLM returns valid CompileDelta → DB reflects changes."""
        # Pre-populate a bullet to update
        existing_bid = await _insert_bullet(
            db_path, project_id, content="Old task info",
        )

        delta = CompileDelta(
            add=[BulletAdd(category="note", content="New note from compile", source="notion_session")],
            update=[BulletUpdate(bullet_id=existing_bid, content="Updated task info")],
        )

        mock_llm = AsyncMock()
        mock_llm.compile = AsyncMock(return_value=delta)

        from src.models import HarvestedItem
        mock_harvested = [
            HarvestedItem(
                source="notion_todo", source_id="n1", project_slug="test-project",
                category="task", content="Some harvested data", timestamp=_now(),
            )
        ]

        with patch("src.compiler.harvest_all", return_value=mock_harvested):
            result = await run_compile(
                project_slug="test-project",
                settings=settings,
                llm_client=mock_llm,
            )

        assert result["bullets_added"] == 1
        assert result["bullets_updated"] == 1
        assert result["error"] is None

        # Verify DB state
        db = await get_db(db_path)
        cursor = await db.execute(
            "SELECT content FROM bullets WHERE id = ?", (existing_bid,)
        )
        row = await cursor.fetchone()
        assert row[0] == "Updated task info"

        cursor = await db.execute(
            "SELECT COUNT(*) FROM bullets WHERE project_id = ?", (project_id,)
        )
        count = (await cursor.fetchone())[0]
        assert count == 2  # original + 1 added
        await db.close()

    @pytest.mark.asyncio
    async def test_empty_harvest_skips_llm(self, db_path, project_id, settings):
        """No harvested data → LLM not called."""
        mock_llm = AsyncMock()
        mock_llm.compile = AsyncMock(return_value=None)

        with patch("src.compiler.harvest_all", return_value=[]):
            result = await run_compile(
                project_slug="test-project",
                settings=settings,
                llm_client=mock_llm,
            )

        # LLM should not have been called
        mock_llm.compile.assert_not_called()
        assert result["bullets_added"] == 0

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self, db_path, project_id, settings):
        """LLM returns None → compile skips gracefully, no crash."""
        mock_llm = AsyncMock()
        mock_llm.compile = AsyncMock(return_value=None)

        from src.models import HarvestedItem
        mock_harvested = [
            HarvestedItem(
                source="lcm", source_id="l1", project_slug="test-project",
                category="note", content="Some data", timestamp=_now(),
            )
        ]

        with patch("src.compiler.harvest_all", return_value=mock_harvested):
            result = await run_compile(
                project_slug="test-project",
                settings=settings,
                llm_client=mock_llm,
            )

        assert result["bullets_added"] == 0
        assert result["error"] is None  # Not an error, just a skip

    @pytest.mark.asyncio
    async def test_compile_records_run(self, db_path, project_id, settings):
        """Compile run is recorded in compile_runs table."""
        mock_llm = AsyncMock()
        mock_llm.compile = AsyncMock(return_value=CompileDelta())

        from src.models import HarvestedItem
        mock_harvested = [
            HarvestedItem(
                source="notion_todo", source_id="n1", project_slug="test-project",
                category="task", content="Data", timestamp=_now(),
            )
        ]

        with patch("src.compiler.harvest_all", return_value=mock_harvested):
            result = await run_compile(
                project_slug="test-project",
                settings=settings,
                llm_client=mock_llm,
            )

        db = await get_db(db_path)
        cursor = await db.execute(
            "SELECT * FROM compile_runs WHERE id = ?", (result["id"],)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["completed_at"] is not None
        await db.close()
