"""Telegram alerts + email digest generation and delivery."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader
from telegram import Bot

from src.config import Settings
from src.database import get_db

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)


# ---------------------------------------------------------------------------
# Digest generation
# ---------------------------------------------------------------------------

async def generate_digest(settings: Settings) -> dict:
    """Query all active projects, gather stale bullets, build digest data."""
    db = await get_db(settings.context_engine_db)
    try:
        now = datetime.now(timezone.utc)

        # Get active projects
        cursor = await db.execute(
            "SELECT id, name, slug, status FROM projects WHERE status = 'active'"
        )
        projects = [dict(row) for row in await cursor.fetchall()]

        all_stale_items: list[dict] = []
        new_blockers: list[dict] = []
        project_details: list[dict] = []
        stale_count = 0

        threshold_map = {
            "task": settings.staleness_hours_task,
            "decision": settings.staleness_hours_decision,
            "blocker": settings.staleness_hours_blocker,
            "tech_state": settings.staleness_hours_tech_state,
            "note": settings.staleness_hours_note,
        }

        for proj in projects:
            cursor = await db.execute(
                "SELECT id, category, content, status, last_verified_at, created_at "
                "FROM bullets WHERE project_id = ? AND status = 'active'",
                (proj["id"],),
            )
            bullets = [dict(row) for row in await cursor.fetchall()]

            open_tasks: list[dict] = []
            stale_items: list[dict] = []
            recent_decisions: list[dict] = []
            blockers: list[dict] = []
            next_steps: list[dict] = []

            for b in bullets:
                verified = datetime.fromisoformat(b["last_verified_at"])
                if verified.tzinfo is None:
                    verified = verified.replace(tzinfo=timezone.utc)
                hours_since = (now - verified).total_seconds() / 3600
                staleness_days = int(hours_since / 24)

                threshold = threshold_map.get(b["category"], 168)
                is_stale = hours_since > threshold if threshold > 0 else True

                item = {
                    "content": b["content"],
                    "project_name": proj["name"],
                    "staleness_days": staleness_days,
                    "category": b["category"],
                }

                if b["category"] == "task":
                    open_tasks.append(item)
                elif b["category"] == "decision":
                    recent_decisions.append(item)
                elif b["category"] == "blocker":
                    blockers.append(item)
                    new_blockers.append(item)
                elif b["category"] == "note":
                    next_steps.append(item)

                if is_stale:
                    stale_items.append(item)
                    all_stale_items.append(item)
                    stale_count += 1

            project_details.append({
                "name": proj["name"],
                "slug": proj["slug"],
                "status": proj["status"],
                "open_tasks": open_tasks,
                "stale_items": stale_items,
                "recent_decisions": recent_decisions,
                "blockers": blockers,
                "next_steps": next_steps,
            })

        # Render telegram text
        tg_template = _jinja.get_template("digest_telegram.md")
        telegram_text = tg_template.render(
            stale_count=stale_count,
            stale_items=all_stale_items,
            new_blockers=new_blockers,
        ).strip()

        # Truncate to Telegram limit
        if len(telegram_text) > 4096:
            telegram_text = telegram_text[:4093] + "..."

        # Render email HTML
        date_str = now.strftime("%Y-%m-%d")
        email_template = _jinja.get_template("digest_email.html")
        email_html = email_template.render(
            date=date_str,
            stale_count=stale_count,
            projects=project_details,
            generated_at=now.isoformat(),
        )

        subject = f"CP7 Context Digest — {date_str} — {stale_count} stale items"

        return {
            "stale_count": stale_count,
            "telegram_text": telegram_text,
            "email_html": email_html,
            "email_subject": subject,
            "summary_text": telegram_text,
            "generated_at": now.isoformat(),
        }
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

async def send_telegram(digest_text: str, settings: Settings) -> bool:
    """Send digest text via Telegram bot. Returns True on success."""
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured, skipping Telegram send")
        return False
    try:
        bot = Bot(token=settings.telegram_bot_token)
        async with bot:
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=digest_text,
                parse_mode="Markdown",
            )
        logger.info("Telegram digest sent to chat %s", settings.telegram_chat_id)
        return True
    except Exception:
        logger.exception("Failed to send Telegram digest")
        return False


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

async def send_email(subject: str, html_body: str, settings: Settings) -> bool:
    """Send HTML email via Gmail SMTP. Returns True on success."""
    if not settings.gmail_address or not settings.gmail_app_password:
        logger.warning("Gmail credentials not configured, skipping email send")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.gmail_address
        msg["To"] = settings.gmail_address
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=settings.gmail_address,
            password=settings.gmail_app_password,
        )
        logger.info("Email digest sent to %s", settings.gmail_address)
        return True
    except Exception:
        logger.exception("Failed to send email digest")
        return False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_digest(settings: Settings, morning: bool = False) -> dict:
    """Generate digest, send alerts, record in DB.

    Args:
        settings: Application settings.
        morning: If True, always send email summary (even if nothing stale).

    Returns:
        Digest record dict.
    """
    digest = await generate_digest(settings)
    stale_count = digest["stale_count"]

    sent_telegram = False
    sent_email = False

    # Telegram: send if stale items exist
    if stale_count > 0:
        sent_telegram = await send_telegram(digest["telegram_text"], settings)

    # Email: send if morning run (always) or could also be triggered by stale
    if morning:
        sent_email = await send_email(
            digest["email_subject"], digest["email_html"], settings
        )

    # Record digest in DB (even if both sends fail)
    digest_id = str(uuid.uuid4())
    db = await get_db(settings.context_engine_db)
    try:
        await db.execute(
            "INSERT INTO digests (id, generated_at, stale_count, summary_text, "
            "sent_telegram, sent_email) VALUES (?, ?, ?, ?, ?, ?)",
            (
                digest_id,
                digest["generated_at"],
                stale_count,
                digest["summary_text"],
                1 if sent_telegram else 0,
                1 if sent_email else 0,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "id": digest_id,
        "generated_at": digest["generated_at"],
        "stale_count": stale_count,
        "summary_text": digest["summary_text"],
        "sent_telegram": sent_telegram,
        "sent_email": sent_email,
    }
