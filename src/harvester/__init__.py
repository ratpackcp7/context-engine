"""Harvester package — collects raw data from all sources."""

from __future__ import annotations

import logging

from src.models import HarvestedItem

from .lcm import harvest_lcm
from .notion import harvest_sessions, harvest_todos

logger = logging.getLogger(__name__)

__all__ = ["harvest_all", "harvest_todos", "harvest_sessions", "harvest_lcm"]


async def harvest_all(
    project_slug: str,
    since: str | None = None,
) -> list[HarvestedItem]:
    """Run all harvesters and deduplicate by source_id.

    Returns combined list[HarvestedItem] with duplicates removed.
    """
    todos = await harvest_todos(project_slug, since)
    sessions = await harvest_sessions(project_slug, since)
    lcm = await harvest_lcm(project_slug, since)

    all_items = todos + sessions + lcm

    # Deduplicate by source_id (keep first occurrence)
    seen: set[str] = set()
    deduped: list[HarvestedItem] = []
    for item in all_items:
        if item.source_id is None:
            deduped.append(item)
            continue
        key = f"{item.source}:{item.source_id}"
        if key not in seen:
            seen.add(key)
            deduped.append(item)
        else:
            logger.debug("Deduped %s item: %s", item.source, item.source_id)

    return deduped
