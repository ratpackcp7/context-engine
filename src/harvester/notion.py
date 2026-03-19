"""Notion harvester — To-Do Tracker + Session Logs databases."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from src.config import Settings
from src.models import HarvestedItem

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
RATE_LIMIT_DELAY = 0.4  # 400ms between requests per Fix 6
MAX_ITEMS = 100  # Cap per harvest per Fix 6


def _notion_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _extract_title(properties: dict) -> str:
    """Extract title text from a Notion page's properties."""
    for prop in properties.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in parts)
    return ""


def _extract_rich_text(properties: dict, name: str) -> str:
    """Extract rich_text value from a named property."""
    prop = properties.get(name)
    if not prop or prop.get("type") != "rich_text":
        return ""
    parts = prop.get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in parts)


def _extract_select(properties: dict, name: str) -> str:
    """Extract select value from a named property."""
    prop = properties.get(name)
    if not prop or prop.get("type") != "select":
        return ""
    select = prop.get("select")
    return select.get("name", "") if select else ""


def _extract_multi_select(properties: dict, name: str) -> list[str]:
    """Extract multi_select values from a named property."""
    prop = properties.get(name)
    if not prop or prop.get("type") != "multi_select":
        return []
    return [s.get("name", "") for s in prop.get("multi_select", [])]


def _extract_status(properties: dict, name: str) -> str:
    """Extract status value from a named property."""
    prop = properties.get(name)
    if not prop or prop.get("type") != "status":
        return ""
    status = prop.get("status")
    return status.get("name", "") if status else ""


async def _query_database(
    client: httpx.AsyncClient,
    token: str,
    database_id: str,
    since: str | None = None,
    max_items: int = MAX_ITEMS,
) -> list[dict]:
    """Query a Notion database with pagination and rate limiting.

    Returns raw page objects up to max_items.
    """
    url = f"{NOTION_API_BASE}/databases/{database_id}/query"
    headers = _notion_headers(token)

    body: dict = {"page_size": min(max_items, 100)}

    # Filter by last_edited_time if since is provided
    if since:
        body["filter"] = {
            "timestamp": "last_edited_time",
            "last_edited_time": {"after": since},
        }

    results: list[dict] = []
    has_more = True
    start_cursor: str | None = None

    while has_more and len(results) < max_items:
        if start_cursor:
            body["start_cursor"] = start_cursor

        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

        if has_more:
            await asyncio.sleep(RATE_LIMIT_DELAY)

    return results[:max_items]


async def harvest_todos(
    project_slug: str,
    since: str | None = None,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[HarvestedItem]:
    """Harvest items from Notion To-Do Tracker database."""
    settings = settings or Settings()
    if not settings.notion_api_token or not settings.notion_todo_db:
        logger.warning("Notion API token or To-Do DB ID not configured, skipping")
        return []

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        pages = await _query_database(
            client, settings.notion_api_token, settings.notion_todo_db, since
        )

        items: list[HarvestedItem] = []
        for page in pages:
            props = page.get("properties", {})
            title = _extract_title(props)
            if not title:
                continue

            # Build content from available properties
            status = _extract_status(props, "Status") or _extract_select(props, "Status")
            tags = _extract_multi_select(props, "Tags") or _extract_multi_select(props, "Project")
            notes = _extract_rich_text(props, "Notes") or _extract_rich_text(props, "Description")

            # Check if this item is tagged for the requested project
            # Match by tag/project or include all if no tags
            slug_lower = project_slug.lower().replace("-", " ")
            tag_match = any(slug_lower in t.lower().replace("-", " ") for t in tags)
            title_match = slug_lower in title.lower().replace("-", " ")
            if tags and not tag_match and not title_match:
                continue

            content_parts = [title]
            if status:
                content_parts.append(f"[{status}]")
            if notes:
                content_parts.append(f"— {notes}")

            # Guess category from status
            category = "task"
            if status and status.lower() in ("done", "complete", "completed"):
                category = "note"

            timestamp = page.get("last_edited_time", datetime.now(timezone.utc).isoformat())

            items.append(
                HarvestedItem(
                    source="notion_todo",
                    source_id=page.get("id"),
                    project_slug=project_slug,
                    category=category,
                    content=" ".join(content_parts),
                    timestamp=timestamp,
                )
            )
        return items

    finally:
        if own_client:
            await client.aclose()


async def harvest_sessions(
    project_slug: str,
    since: str | None = None,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[HarvestedItem]:
    """Harvest items from Notion Session Logs database."""
    settings = settings or Settings()
    if not settings.notion_api_token or not settings.notion_session_db:
        logger.warning("Notion API token or Session DB ID not configured, skipping")
        return []

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        pages = await _query_database(
            client, settings.notion_api_token, settings.notion_session_db, since
        )

        items: list[HarvestedItem] = []
        for page in pages:
            props = page.get("properties", {})
            title = _extract_title(props)
            if not title:
                continue

            # Check project association
            tags = _extract_multi_select(props, "Project") or _extract_multi_select(props, "Tags")
            slug_lower = project_slug.lower().replace("-", " ")
            tag_match = any(slug_lower in t.lower().replace("-", " ") for t in tags)
            title_match = slug_lower in title.lower().replace("-", " ")
            if tags and not tag_match and not title_match:
                continue

            summary = _extract_rich_text(props, "Summary") or _extract_rich_text(props, "Notes")
            content = f"{title}: {summary}" if summary else title

            timestamp = page.get("last_edited_time", datetime.now(timezone.utc).isoformat())

            items.append(
                HarvestedItem(
                    source="notion_session",
                    source_id=page.get("id"),
                    project_slug=project_slug,
                    category="note",
                    content=content,
                    timestamp=timestamp,
                )
            )
        return items

    finally:
        if own_client:
            await client.aclose()
