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
    """Search LCM-Lite for sessions matching project_slug."""
    settings = settings or Settings()
    if not settings.lcm_lite_url or not settings.lcm_lite_token:
        logger.warning("LCM-Lite URL or token not configured, skipping")
        return []

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        headers = {"Authorization": f"Bearer {settings.lcm_lite_token}"}
        # Replace hyphens with spaces — FTS5 treats hyphens as NOT operator
        safe_query = project_slug.replace("-", " ")
        params: dict = {"q": safe_query, "limit": 10}
        if since:
            params["after"] = since

        resp = await client.get(
            f"{settings.lcm_lite_url}/search",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data if isinstance(data, list) else data.get("results", [])

        items: list[HarvestedItem] = []
        for entry in results:
            timestamp = (
                entry.get("created_at")
                or entry.get("timestamp")
                or datetime.now(timezone.utc).isoformat()
            )

            # Extract content from LCM-Lite search result format
            snippet = entry.get("snippet", "")
            session_id = entry.get("session_id", "")
            message_id = entry.get("message_id", "")
            project = entry.get("project", "")

            # Only include results that match our project
            slug_words = set(project_slug.lower().replace("-", " ").split())
            result_project = project.lower().replace("-", " ")
            snippet_lower = snippet.lower()
            if not any(w in result_project or w in snippet_lower for w in slug_words):
                continue

            content = snippet[:500] if snippet else f"Session {session_id}"
            if not content.strip():
                continue

            items.append(
                HarvestedItem(
                    source="lcm",
                    source_id=message_id or None,
                    project_slug=project_slug,
                    category="note",
                    content=content,
                    timestamp=timestamp,
                )
            )

        logger.info("LCM-Lite: %d results for '%s'", len(items), safe_query)
        return items

    except Exception as exc:
        logger.warning("LCM-Lite harvest failed for %s: %s", project_slug, exc)
        return []

    finally:
        if own_client:
            await client.aclose()
