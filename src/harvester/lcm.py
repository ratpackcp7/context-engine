"""LCM-Lite session search harvester."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from src.config import Settings
from src.models import HarvestedItem

logger = logging.getLogger(__name__)


async def harvest_lcm(
    project_slug: str,
    since: str | None = None,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[HarvestedItem]:
    """Search LCM-Lite for sessions matching project_slug.

    GET {lcm_url}/search?q={project_slug}&limit=10
    """
    settings = settings or Settings()
    if not settings.lcm_lite_url or not settings.lcm_lite_token:
        logger.warning("LCM-Lite URL or token not configured, skipping")
        return []

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        headers = {"Authorization": f"Bearer {settings.lcm_lite_token}"}
        params = {"q": project_slug, "limit": 10}

        resp = await client.get(
            f"{settings.lcm_lite_url}/search",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        # LCM-Lite returns a list of session objects (or results key)
        results = data if isinstance(data, list) else data.get("results", [])

        items: list[HarvestedItem] = []
        for entry in results:
            # Extract timestamp — try common field names
            timestamp = (
                entry.get("timestamp")
                or entry.get("created_at")
                or entry.get("date")
                or datetime.now(timezone.utc).isoformat()
            )

            # Filter by since if provided
            if since:
                try:
                    entry_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    if entry_dt < since_dt:
                        continue
                except (ValueError, AttributeError):
                    pass

            # Extract content
            title = entry.get("title", entry.get("name", ""))
            summary = entry.get("summary", entry.get("content", entry.get("text", "")))
            content = f"{title}: {summary}" if title and summary else title or summary

            if not content:
                continue

            source_id = str(entry.get("id", entry.get("session_id", ""))) or None

            items.append(
                HarvestedItem(
                    source="lcm",
                    source_id=source_id,
                    project_slug=project_slug,
                    category="note",
                    content=content,
                    timestamp=timestamp,
                )
            )

        return items

    except httpx.HTTPError as exc:
        logger.error("LCM-Lite harvest failed: %s", exc)
        return []

    finally:
        if own_client:
            await client.aclose()
