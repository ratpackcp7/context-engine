"""Tests for all API endpoints."""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Set test env vars before importing app
os.environ["CONTEXT_ENGINE_TOKEN"] = "testtoken"
os.environ["CONTEXT_ENGINE_DB"] = ""  # Will be overridden per test
os.environ["GEMINI_API_KEY"] = ""

from src.database import init_db
from src.main import app

TOKEN = "testtoken"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client(tmp_path):
    """Create a test client with a fresh temporary database."""
    db_path = str(tmp_path / "test.db")
    # Patch the settings to use the temp DB
    from src.dependencies import _settings
    original_db = _settings.context_engine_db
    _settings.context_engine_db = db_path
    _settings.context_engine_token = TOKEN

    # Init the DB synchronously via the event loop
    import asyncio
    asyncio.get_event_loop().run_until_complete(init_db(db_path))

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    _settings.context_engine_db = original_db


# --- Health ---

class TestHealth:
    def test_health_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["db"] == "connected"


# --- Auth ---

class TestAuth:
    def test_no_token_returns_401(self, client):
        resp = client.get("/projects")
        assert resp.status_code in (401, 403)

    def test_wrong_token_returns_401(self, client):
        resp = client.get("/projects", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_valid_token(self, client):
        resp = client.get("/projects", headers=AUTH)
        assert resp.status_code == 200


# --- Projects ---

class TestProjects:
    def test_create_and_list(self, client):
        # Create
        resp = client.post(
            "/projects",
            json={"name": "Test Project", "slug": "test-project"},
            headers=AUTH,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == "test-project"
        assert data["status"] == "active"
        assert "id" in data

        # List
        resp = client.get("/projects", headers=AUTH)
        assert resp.status_code == 200
        projects = resp.json()["projects"]
        assert len(projects) == 1
        assert projects[0]["slug"] == "test-project"
        assert projects[0]["bullet_count"] == 0

    def test_duplicate_slug(self, client):
        client.post(
            "/projects",
            json={"name": "P1", "slug": "dup"},
            headers=AUTH,
        )
        resp = client.post(
            "/projects",
            json={"name": "P2", "slug": "dup"},
            headers=AUTH,
        )
        assert resp.status_code == 409


# --- Playbook ---

class TestPlaybook:
    def test_playbook_markdown(self, client):
        client.post(
            "/projects",
            json={"name": "Finance Hub", "slug": "finance-hub"},
            headers=AUTH,
        )
        resp = client.get("/projects/finance-hub/playbook", headers=AUTH)
        assert resp.status_code == 200
        text = resp.json()
        assert "Finance Hub — Project Playbook" in text
        assert "## Current Status" in text
        assert "## Open Tasks" in text
        assert "## Recent Decisions" in text
        assert "## Active Blockers" in text
        assert "## Technical State" in text
        assert "## Stale Items" in text
        assert "## Next Steps" in text

    def test_playbook_json(self, client):
        client.post(
            "/projects",
            json={"name": "Test", "slug": "test"},
            headers=AUTH,
        )
        resp = client.get("/projects/test/playbook?format=json", headers=AUTH)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_playbook_not_found(self, client):
        resp = client.get("/projects/nope/playbook", headers=AUTH)
        assert resp.status_code == 404


# --- Sessions ---

class TestSessions:
    def test_create_session(self, client):
        # Create project first
        client.post(
            "/projects",
            json={"name": "Test", "slug": "test"},
            headers=AUTH,
        )
        resp = client.post(
            "/sessions",
            json={
                "project_slug": "test",
                "summary": "Did some work",
                "decisions": ["Used OpenRouter"],
                "open_items": ["Fix tests"],
                "tech_changes": [],
                "next_steps": ["Deploy"],
            },
            headers=AUTH,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["project_slug"] == "test"
        assert "id" in data
        assert "created_at" in data

    def test_session_project_not_found(self, client):
        resp = client.post(
            "/sessions",
            json={
                "project_slug": "nonexistent",
                "summary": "Test",
            },
            headers=AUTH,
        )
        assert resp.status_code == 404


# --- Compile ---

class TestCompile:
    def test_trigger_compile(self, client):
        client.post(
            "/projects",
            json={"name": "Test", "slug": "test"},
            headers=AUTH,
        )
        resp = client.post("/compile", headers=AUTH)
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "started"
        assert "test" in data["projects"]

    def test_compile_run_not_found(self, client):
        resp = client.get("/compile/nonexistent-id", headers=AUTH)
        assert resp.status_code == 404


# --- Digest ---

class TestDigest:
    def test_no_digests(self, client):
        resp = client.get("/digest/latest", headers=AUTH)
        assert resp.status_code == 404


# --- Bullet Feedback ---

class TestBulletFeedback:
    def test_feedback_not_found(self, client):
        resp = client.post(
            "/bullets/nonexistent/feedback",
            json={"feedback": "helpful"},
            headers=AUTH,
        )
        assert resp.status_code == 404
