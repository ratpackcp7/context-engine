"""Tests for digest generation, Telegram alerts, and email delivery."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.config import Settings
from src.database import init_db, get_db
from src.digest import generate_digest, run_digest, send_email, send_telegram


@pytest.fixture
def settings(tmp_path):
    db_path = str(tmp_path / "test.db")
    return Settings(
        context_engine_db=db_path,
        telegram_bot_token="test-token",
        telegram_chat_id="12345",
        gmail_address="test@gmail.com",
        gmail_app_password="app-pass",
        staleness_hours_task=48,
        staleness_hours_decision=168,
        staleness_hours_blocker=0,
        staleness_hours_tech_state=168,
        staleness_hours_note=336,
    )


@pytest_asyncio.fixture
async def db_with_data(settings):
    """Initialize DB and insert test projects + bullets."""
    await init_db(settings.context_engine_db)
    db = await get_db(settings.context_engine_db)

    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=5)).isoformat()
    recent = (now - timedelta(hours=1)).isoformat()

    # Project 1: has stale items
    proj1_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO projects (id, name, slug, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (proj1_id, "Finance Hub", "finance-hub", "active", now.isoformat(), now.isoformat()),
    )

    # Stale task (5 days old, threshold 48h)
    await db.execute(
        "INSERT INTO bullets (id, project_id, category, content, source, status, "
        "created_at, updated_at, last_verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), proj1_id, "task", "Task 002 AI categorization",
         "session_handover", "active", old, old, old),
    )

    # Fresh decision (1 hour old)
    await db.execute(
        "INSERT INTO bullets (id, project_id, category, content, source, status, "
        "created_at, updated_at, last_verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), proj1_id, "decision", "Using OpenRouter for categorization",
         "session_handover", "active", recent, recent, recent),
    )

    # Blocker (always stale with threshold=0)
    await db.execute(
        "INSERT INTO bullets (id, project_id, category, content, source, status, "
        "created_at, updated_at, last_verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), proj1_id, "blocker", "Waiting on API credentials",
         "session_handover", "active", recent, recent, recent),
    )

    # Project 2: no stale items
    proj2_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO projects (id, name, slug, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (proj2_id, "CBA", "cba", "active", now.isoformat(), now.isoformat()),
    )

    # Fresh task
    await db.execute(
        "INSERT INTO bullets (id, project_id, category, content, source, status, "
        "created_at, updated_at, last_verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), proj2_id, "task", "Longevity cost model",
         "session_handover", "active", recent, recent, recent),
    )

    await db.commit()
    await db.close()
    return settings


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_digest_with_stale_items(db_with_data):
    """Digest shows stale items and blockers."""
    settings = db_with_data
    digest = await generate_digest(settings)

    assert digest["stale_count"] >= 2  # stale task + blocker (always stale)
    assert "stale" in digest["telegram_text"].lower() or "⚠️" in digest["telegram_text"]
    assert "Finance Hub" in digest["telegram_text"]
    assert "email_html" in digest
    assert "CP7 Context Digest" in digest["email_subject"]


@pytest.mark.asyncio
async def test_generate_digest_no_stale(settings):
    """Digest with no data has zero stale items."""
    await init_db(settings.context_engine_db)
    digest = await generate_digest(settings)

    assert digest["stale_count"] == 0
    assert "No stale items" in digest["telegram_text"] or "✅" in digest["telegram_text"]


@pytest.mark.asyncio
async def test_generate_digest_multiple_projects(db_with_data):
    """Email template renders per-project sections."""
    settings = db_with_data
    digest = await generate_digest(settings)

    assert "Finance Hub" in digest["email_html"]
    assert "CBA" in digest["email_html"]


@pytest.mark.asyncio
async def test_telegram_truncation(db_with_data):
    """Telegram text must not exceed 4096 chars."""
    settings = db_with_data
    digest = await generate_digest(settings)
    assert len(digest["telegram_text"]) <= 4096


# ---------------------------------------------------------------------------
# send_telegram
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_telegram_success(settings):
    """Telegram send returns True on success."""
    mock_bot = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock(return_value=False)
    mock_bot.send_message = AsyncMock()

    with patch("src.digest.Bot", return_value=mock_bot):
        result = await send_telegram("test message", settings)

    assert result is True
    mock_bot.send_message.assert_awaited_once_with(
        chat_id="12345", text="test message", parse_mode="Markdown"
    )


@pytest.mark.asyncio
async def test_send_telegram_failure(settings):
    """Telegram send returns False on error without raising."""
    mock_bot = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock(return_value=False)
    mock_bot.send_message = AsyncMock(side_effect=Exception("Network error"))

    with patch("src.digest.Bot", return_value=mock_bot):
        result = await send_telegram("test message", settings)

    assert result is False


@pytest.mark.asyncio
async def test_send_telegram_no_token(settings):
    """Skip Telegram when token is empty."""
    settings.telegram_bot_token = ""
    result = await send_telegram("test", settings)
    assert result is False


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_email_success(settings):
    """Email send returns True on success."""
    with patch("src.digest.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        result = await send_email("Subject", "<h1>Hi</h1>", settings)

    assert result is True
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_email_failure(settings):
    """Email send returns False on error without raising."""
    with patch("src.digest.aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("SMTP error")):
        result = await send_email("Subject", "<h1>Hi</h1>", settings)

    assert result is False


@pytest.mark.asyncio
async def test_send_email_no_credentials(settings):
    """Skip email when credentials are empty."""
    settings.gmail_address = ""
    result = await send_email("Subject", "<h1>Hi</h1>", settings)
    assert result is False


# ---------------------------------------------------------------------------
# run_digest orchestrator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_digest_stale_sends_telegram(db_with_data):
    """Stale items trigger Telegram alert."""
    settings = db_with_data

    with patch("src.digest.send_telegram", new_callable=AsyncMock, return_value=True) as mock_tg, \
         patch("src.digest.send_email", new_callable=AsyncMock, return_value=False) as mock_email:
        result = await run_digest(settings, morning=False)

    assert result["sent_telegram"] is True
    assert result["sent_email"] is False
    mock_tg.assert_awaited_once()
    mock_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_digest_morning_sends_email(db_with_data):
    """Morning run sends email regardless of stale count."""
    settings = db_with_data

    with patch("src.digest.send_telegram", new_callable=AsyncMock, return_value=True) as mock_tg, \
         patch("src.digest.send_email", new_callable=AsyncMock, return_value=True) as mock_email:
        result = await run_digest(settings, morning=True)

    assert result["sent_email"] is True
    mock_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_failure_doesnt_prevent_email(db_with_data):
    """If Telegram fails, email should still be attempted."""
    settings = db_with_data

    with patch("src.digest.send_telegram", new_callable=AsyncMock, return_value=False) as mock_tg, \
         patch("src.digest.send_email", new_callable=AsyncMock, return_value=True) as mock_email:
        result = await run_digest(settings, morning=True)

    assert result["sent_telegram"] is False
    assert result["sent_email"] is True
    mock_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_digest_record_saved_on_double_failure(db_with_data):
    """Digest record saved to DB even when both sends fail."""
    settings = db_with_data

    with patch("src.digest.send_telegram", new_callable=AsyncMock, return_value=False), \
         patch("src.digest.send_email", new_callable=AsyncMock, return_value=False):
        result = await run_digest(settings, morning=True)

    assert result["sent_telegram"] is False
    assert result["sent_email"] is False
    assert result["id"] is not None

    # Verify record in DB
    db = await get_db(settings.context_engine_db)
    try:
        cursor = await db.execute("SELECT * FROM digests WHERE id = ?", (result["id"],))
        row = await cursor.fetchone()
        assert row is not None
        assert row["sent_telegram"] == 0
        assert row["sent_email"] == 0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_run_digest_no_stale_no_telegram(settings):
    """No stale items = no Telegram alert sent."""
    await init_db(settings.context_engine_db)

    with patch("src.digest.send_telegram", new_callable=AsyncMock) as mock_tg, \
         patch("src.digest.send_email", new_callable=AsyncMock, return_value=True):
        result = await run_digest(settings, morning=True)

    assert result["stale_count"] == 0
    mock_tg.assert_not_awaited()
