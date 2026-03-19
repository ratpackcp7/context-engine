# Task 002: Project scaffold, dependencies, config, DB schema, Pydantic models

## Objective

Set up the project structure, install dependencies, create config loading, database schema, and all Pydantic models.

## Context

Fresh project directory at `/home/chris/projects/context-engine/`. SPEC.md exists.

## Spec Reference

SPEC.md: File Tree, Data Models, External Dependencies, Environment, Review Fixes 1-4.

## Operation Order

1. Create all directories: `src/`, `src/harvester/`, `src/api/`, `src/templates/`, `data/`, `scripts/`, `tests/`
2. Write `requirements.txt` (exact pinned versions from SPEC.md)
3. Write `.env.example` with ALL env vars (including Review Fix 4 staleness thresholds per category)
4. Create venv: `python3.12 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
5. Write `src/__init__.py`, `src/harvester/__init__.py`, `src/api/__init__.py` (empty)
6. Write `src/config.py` — Pydantic Settings
7. Write `src/models.py` — ALL Pydantic models including HarvestedItem, CompileDelta per Review Fix 2/3
8. Write `src/database.py` — async SQLite with WAL+busy_timeout per Review Fix 1, all CREATE TABLE
9. Write placeholder templates: `src/templates/compile_prompt.md`, `digest_telegram.md`, `digest_email.html`
10. Write `data/.gitkeep`

## Deliverables

- [ ] `requirements.txt`
- [ ] `.env.example`
- [ ] `src/__init__.py`, `src/harvester/__init__.py`, `src/api/__init__.py`
- [ ] `src/config.py` — Settings class with nested config groups
- [ ] `src/models.py` — ProjectCreate, ProjectResponse, SessionCreate, SessionResponse, BulletResponse, BulletFeedback, HarvestedItem, BulletAdd, BulletUpdate, BulletArchive, CompileDelta, CompileRequest, CompileRunResponse, DigestResponse, HealthResponse
- [ ] `src/database.py` — init_db(), get_db(), all 5 tables (projects, bullets, sessions, digests, compile_runs)
- [ ] Template placeholders
- [ ] `data/.gitkeep`
- [ ] `venv/` with deps installed

## Acceptance Criteria

1. [ ] `source venv/bin/activate && python -c "from src.config import Settings; print('Config OK')"`
2. [ ] `python -c "from src.models import CompileDelta, HarvestedItem, SessionCreate; print('Models OK')"`
3. [ ] `python -c "import asyncio; from src.database import init_db; asyncio.run(init_db('data/test.db')); print('DB OK')"`
4. [ ] `sqlite3 data/test.db '.tables'` shows all 5 tables
5. [ ] `sqlite3 data/test.db 'PRAGMA journal_mode'` returns `wal`

## Notes

- staleness_days is COMPUTED on read via SQL, not stored as a column
- All timestamps: ISO 8601 UTC strings
- Database path comes from config (CONTEXT_ENGINE_DB env var)
