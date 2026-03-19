"""Tests for harvester modules — Notion + LCM-Lite with mocked HTTP."""

from __future__ import annotations

import json

import httpx
import pytest

from src.config import Settings
from src.harvester import harvest_all
from src.harvester.lcm import harvest_lcm
from src.harvester.notion import harvest_sessions, harvest_todos


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def notion_settings() -> Settings:
    """Settings with Notion configured."""
    return Settings(
        notion_api_token="test-token",
        notion_todo_db="todo-db-id",
        notion_session_db="session-db-id",
        lcm_lite_url="http://localhost:8400",
        lcm_lite_token="lcm-token",
    )


def _notion_page(page_id: str, title: str, tags: list[str] | None = None,
                 status: str = "In Progress", last_edited: str = "2026-03-19T10:00:00Z") -> dict:
    """Build a minimal Notion page object for testing."""
    properties: dict = {
        "Name": {
            "type": "title",
            "title": [{"plain_text": title}],
        },
        "Status": {
            "type": "status",
            "status": {"name": status} if status else None,
        },
    }
    if tags is not None:
        properties["Project"] = {
            "type": "multi_select",
            "multi_select": [{"name": t} for t in tags],
        }
    return {
        "id": page_id,
        "last_edited_time": last_edited,
        "properties": properties,
    }


def _notion_response(pages: list[dict], has_more: bool = False,
                     next_cursor: str | None = None) -> dict:
    return {
        "results": pages,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


# ---------------------------------------------------------------------------
# Notion To-Do Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_harvest_todos_basic(notion_settings: Settings):
    """Basic todo harvest returns HarvestedItems."""
    page = _notion_page("p1", "Fix login bug", tags=["finance-hub"])
    mock_resp = _notion_response([page])

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_resp)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        items = await harvest_todos("finance-hub", settings=notion_settings, client=client)

    assert len(items) == 1
    assert items[0].source == "notion_todo"
    assert items[0].source_id == "p1"
    assert items[0].project_slug == "finance-hub"
    assert "Fix login bug" in items[0].content


@pytest.mark.asyncio
async def test_harvest_todos_filters_by_project(notion_settings: Settings):
    """Items tagged for a different project are excluded."""
    page = _notion_page("p1", "Unrelated task", tags=["other-project"])
    mock_resp = _notion_response([page])

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_resp)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        items = await harvest_todos("finance-hub", settings=notion_settings, client=client)

    assert len(items) == 0


@pytest.mark.asyncio
async def test_harvest_todos_pagination(notion_settings: Settings):
    """Notion pagination with 2 pages returns combined results."""
    page1 = _notion_page("p1", "Task A", tags=["myproject"])
    page2 = _notion_page("p2", "Task B", tags=["myproject"])

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content)
        if "start_cursor" not in body:
            return httpx.Response(200, json=_notion_response([page1], has_more=True, next_cursor="cursor-2"))
        else:
            assert body["start_cursor"] == "cursor-2"
            return httpx.Response(200, json=_notion_response([page2], has_more=False))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        items = await harvest_todos("myproject", settings=notion_settings, client=client)

    assert len(items) == 2
    assert items[0].source_id == "p1"
    assert items[1].source_id == "p2"
    assert call_count == 2


@pytest.mark.asyncio
async def test_harvest_todos_sends_since_filter(notion_settings: Settings):
    """When since is provided, the request includes a last_edited_time filter."""
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json=_notion_response([]))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await harvest_todos(
            "test", since="2026-03-18T00:00:00Z",
            settings=notion_settings, client=client,
        )

    assert "filter" in captured_body
    assert captured_body["filter"]["timestamp"] == "last_edited_time"
    assert captured_body["filter"]["last_edited_time"]["after"] == "2026-03-18T00:00:00Z"


# ---------------------------------------------------------------------------
# Notion Session Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_harvest_sessions_basic(notion_settings: Settings):
    """Basic session harvest returns HarvestedItems."""
    page = _notion_page("s1", "Session: debugging auth", tags=["cba"])
    page["properties"]["Summary"] = {
        "type": "rich_text",
        "rich_text": [{"plain_text": "Fixed the auth flow"}],
    }
    mock_resp = _notion_response([page])

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_resp)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        items = await harvest_sessions("cba", settings=notion_settings, client=client)

    assert len(items) == 1
    assert items[0].source == "notion_session"
    assert "Fixed the auth flow" in items[0].content


# ---------------------------------------------------------------------------
# LCM-Lite Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_harvest_lcm_basic(notion_settings: Settings):
    """LCM-Lite harvest returns HarvestedItems."""
    lcm_data = [
        {
            "id": "lcm-1",
            "title": "Finance Hub session",
            "summary": "Worked on categorization",
            "timestamp": "2026-03-19T08:00:00Z",
        }
    ]

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=lcm_data)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        items = await harvest_lcm("finance-hub", settings=notion_settings, client=client)

    assert len(items) == 1
    assert items[0].source == "lcm"
    assert items[0].source_id == "lcm-1"
    assert "categorization" in items[0].content


@pytest.mark.asyncio
async def test_harvest_lcm_filters_by_since(notion_settings: Settings):
    """LCM items older than since are excluded."""
    lcm_data = [
        {"id": "old", "title": "Old", "summary": "old stuff", "timestamp": "2026-03-01T00:00:00Z"},
        {"id": "new", "title": "New", "summary": "new stuff", "timestamp": "2026-03-19T00:00:00Z"},
    ]

    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=lcm_data)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        items = await harvest_lcm(
            "test", since="2026-03-15T00:00:00Z",
            settings=notion_settings, client=client,
        )

    assert len(items) == 1
    assert items[0].source_id == "new"


@pytest.mark.asyncio
async def test_harvest_lcm_http_error(notion_settings: Settings):
    """LCM harvest returns empty list on HTTP error."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(500, text="Internal Server Error")
    )
    async with httpx.AsyncClient(transport=transport) as client:
        items = await harvest_lcm("test", settings=notion_settings, client=client)

    assert items == []


# ---------------------------------------------------------------------------
# harvest_all + Deduplication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_harvest_all_deduplicates(notion_settings: Settings, monkeypatch):
    """Duplicate source_ids across harvesters are deduplicated."""
    from src.harvester import notion, lcm
    from src.models import HarvestedItem

    dup_item = HarvestedItem(
        source="notion_todo",
        source_id="dup-id",
        project_slug="test",
        category="task",
        content="Duplicate item from todos",
        timestamp="2026-03-19T00:00:00Z",
    )
    dup_item_lcm = HarvestedItem(
        source="lcm",
        source_id="dup-id",  # Same source_id but different source — not deduped
        project_slug="test",
        category="note",
        content="Duplicate item from lcm",
        timestamp="2026-03-19T00:00:00Z",
    )
    dup_item_todo2 = HarvestedItem(
        source="notion_todo",
        source_id="dup-id",  # Same source + source_id — deduped
        project_slug="test",
        category="task",
        content="Duplicate item again",
        timestamp="2026-03-19T00:00:00Z",
    )
    unique_item = HarvestedItem(
        source="notion_session",
        source_id="unique-id",
        project_slug="test",
        category="note",
        content="Unique item",
        timestamp="2026-03-19T00:00:00Z",
    )

    async def mock_todos(slug, since=None, **kw):
        return [dup_item, dup_item_todo2]

    async def mock_sessions(slug, since=None, **kw):
        return [unique_item]

    async def mock_lcm(slug, since=None, **kw):
        return [dup_item_lcm]

    monkeypatch.setattr("src.harvester.harvest_todos", mock_todos)
    monkeypatch.setattr("src.harvester.harvest_sessions", mock_sessions)
    monkeypatch.setattr("src.harvester.harvest_lcm", mock_lcm)

    items = await harvest_all("test")

    # dup_item + unique_item + dup_item_lcm = 3 (dup_item_todo2 deduped with dup_item)
    assert len(items) == 3
    source_ids = [(i.source, i.source_id) for i in items]
    assert ("notion_todo", "dup-id") in source_ids
    assert ("notion_session", "unique-id") in source_ids
    assert ("lcm", "dup-id") in source_ids


@pytest.mark.asyncio
async def test_import_harvest_all():
    """Acceptance: import check."""
    from src.harvester import harvest_all
    assert callable(harvest_all)
    print("Harvester OK")
