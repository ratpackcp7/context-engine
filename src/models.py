"""Pydantic models — request/response schemas and LLM output validation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# --- Project ---

class ProjectCreate(BaseModel):
    name: str
    slug: str
    notion_page_id: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    slug: str
    notion_page_id: str | None = None
    status: str = "active"
    created_at: str
    updated_at: str


class ProjectListItem(BaseModel):
    slug: str
    name: str
    status: str
    bullet_count: int = 0
    stale_count: int = 0
    last_compiled_at: str | None = None
    last_session_at: str | None = None


class ProjectListResponse(BaseModel):
    projects: list[ProjectListItem]


# --- Session ---

class SessionCreate(BaseModel):
    project_slug: str
    summary: str
    decisions: list[str] = []
    open_items: list[str] = []
    tech_changes: list[str] = []
    next_steps: list[str] = []


class SessionResponse(BaseModel):
    id: str
    project_slug: str
    created_at: str


# --- Bullet ---

class BulletResponse(BaseModel):
    id: str
    project_id: str
    category: str
    content: str
    source: str
    source_id: str | None = None
    status: str
    created_at: str
    updated_at: str
    last_verified_at: str
    staleness_days: int
    helpful_count: int = 0
    harmful_count: int = 0


class BulletFeedback(BaseModel):
    feedback: Literal["helpful", "harmful"]


# --- Harvester intermediate schema (Review Fix 3) ---

class HarvestedItem(BaseModel):
    source: Literal["notion_todo", "notion_session", "lcm", "session_handover"]
    source_id: str | None = None
    project_slug: str
    category: str
    content: str
    timestamp: str  # ISO 8601


# --- Compile delta models (Review Fix 2) ---

class BulletAdd(BaseModel):
    category: Literal["task", "decision", "blocker", "tech_state", "note"]
    content: str
    source: str


class BulletUpdate(BaseModel):
    bullet_id: str
    content: str


class BulletArchive(BaseModel):
    bullet_id: str
    reason: str


class CompileDelta(BaseModel):
    add: list[BulletAdd] = []
    update: list[BulletUpdate] = []
    archive: list[BulletArchive] = []


# --- Compile API ---

class CompileRequest(BaseModel):
    project_slug: str | None = None


class CompileRunResponse(BaseModel):
    id: str
    started_at: str
    completed_at: str | None = None
    project_slugs: list[str] = []
    bullets_added: int = 0
    bullets_updated: int = 0
    bullets_archived: int = 0
    llm_provider: str | None = None
    llm_model: str | None = None
    error: str | None = None


# --- Digest ---

class DigestResponse(BaseModel):
    id: str
    generated_at: str
    stale_count: int
    summary_text: str
    sent_telegram: bool
    sent_email: bool


# --- Health ---

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    db: str = "connected"
    llm: str = "gemini"
