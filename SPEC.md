# CP7 Context Engine — SPEC.md

## Problem Statement

Session continuity between claude.ai conversations is broken. State is scattered across five
systems (userMemories blob, Notion session logs, Notion to-do tracker, LCM-Lite, past_chats tool)
with no unified view. Retrieval requires manual commands ("check notion", "save") that don't
happen consistently. When a new conversation starts, there is no reliable way to answer "where
did we leave off on project X?" without searching multiple sources.

Additionally, nothing runs between conversations. Open items go stale without notification.
Decisions made in one session aren't consolidated into project state. The userMemories blob
suffers from context collapse — each edit risks overwriting nuanced details with compressed
summaries.

## Solution

A background service on acerserver that:

1. **Harvests** raw state from Notion, LCM-Lite, and system state
2. **Compiles** per-project "playbooks" using an LLM (ACE-inspired: structured bullets with
   metadata, delta updates only — never full rewrites)
3. **Pushes** a daily digest via Telegram (alerts) + email (summary)
4. **Serves** compiled playbooks via API + bridge scripts for fast context loading in claude.ai

Inspired by the ACE (Agentic Context Engineering) framework: contexts are treated as evolving
playbooks of structured, itemized bullets rather than monolithic text. Each bullet has metadata
(timestamps, source, staleness) and updates are incremental deltas, preventing context collapse.

## Tech Stack

| Component       | Choice                       | Rationale                                                |
|-----------------|------------------------------|----------------------------------------------------------|
| Runtime         | Python 3.12                  | Consistent with LCM-Lite, full ecosystem access          |
| Framework       | FastAPI + uvicorn            | Consistent with LCM-Lite, async-native, lightweight      |
| Database        | SQLite (via aiosqlite)       | Single-file, simple backup, no graph needed              |
| Primary LLM     | Gemini Flash (free BYOK)     | Free tier, fast, excellent summarization quality          |
| Fallback LLM    | Ollama (local, port 11434)   | Zero-cost fallback, fully private, already running        |
| Telegram        | python-telegram-bot          | Existing bot token shared with OpenClaw                  |
| Email           | aiosmtplib + email.mime      | Gmail SMTP with app password                             |
| HTTP client     | httpx                        | Async, used for Notion API + LCM-Lite calls              |
| Deployment      | systemd user service + timer | Consistent with LCM-Lite, lighter than Docker            |

## File Tree

```
/home/chris/projects/context-engine/
├── SPEC.md
├── AGENT_CONTEXT.md
├── tasks/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, lifespan, routes
│   ├── config.py               # Pydantic Settings, env var loading
│   ├── database.py             # SQLite setup, table creation, connection pool
│   ├── models.py               # Pydantic models (request/response schemas)
│   ├── harvester/
│   │   ├── __init__.py
│   │   ├── notion.py           # Notion To-Do Tracker + Session Logs harvester
│   │   ├── lcm.py              # LCM-Lite session search harvester
│   │   └── system.py           # Bridge system state harvester (optional, phase 2)
│   ├── compiler.py             # ACE-inspired compile loop
│   ├── llm.py                  # LLM abstraction (Gemini Flash + Ollama fallback)
│   ├── digest.py               # Telegram + email digest generation and delivery
│   ├── api/
│   │   ├── __init__.py
│   │   ├── sessions.py         # POST /sessions
│   │   ├── projects.py         # CRUD projects, GET playbook
│   │   ├── compile.py          # POST /compile, GET /compile/{run_id}
│   │   └── digest.py           # GET /digest/latest
│   └── templates/
│       ├── compile_prompt.md   # LLM prompt for compile step
│       ├── digest_telegram.md  # Telegram message template
│       └── digest_email.html   # Email HTML template
├── scripts/
│   ├── context_load.sh         # Bridge script: GET playbook
│   └── context_save.sh         # Bridge script: POST session
├── data/                       # Created at runtime
└── tests/
    ├── conftest.py
    ├── test_harvester.py
    ├── test_compiler.py
    ├── test_llm.py
    ├── test_api.py
    └── test_digest.py
```

## Data Models

### projects

| Column          | Type     | Notes                                        |
|-----------------|----------|----------------------------------------------|
| id              | TEXT PK  | UUID                                         |
| name            | TEXT     | Human-readable ("Finance Hub", "CBA")        |
| slug            | TEXT UNQ | URL-safe identifier ("finance-hub", "cba")   |
| notion_page_id  | TEXT     | Notion project page ID (nullable)            |
| status          | TEXT     | "active" / "paused" / "done"                 |
| created_at      | TEXT     | ISO 8601                                     |
| updated_at      | TEXT     | ISO 8601                                     |

### bullets

The core data structure. ACE-inspired: each bullet is an independently updateable unit
of project knowledge with metadata for staleness tracking and feedback scoring.

| Column           | Type     | Notes                                            |
|------------------|----------|--------------------------------------------------|
| id               | TEXT PK  | UUID                                             |
| project_id       | TEXT FK  | References projects.id                           |
| category         | TEXT     | "task" / "decision" / "blocker" / "tech_state" / "note" |
| content          | TEXT     | The actual information                           |
| source           | TEXT     | "notion_todo" / "notion_session" / "lcm" / "session_handover" / "manual" |
| source_id        | TEXT     | Original record ID from source (nullable)        |
| status           | TEXT     | "active" / "stale" / "archived" / "superseded"   |
| created_at       | TEXT     | ISO 8601                                         |
| updated_at       | TEXT     | ISO 8601                                         |
| last_verified_at | TEXT     | ISO 8601, refreshed each compile that confirms   |
| staleness_days   | INTEGER  | Computed: days since last_verified_at             |
| helpful_count    | INTEGER  | ACE feedback: bullet was useful (default 0)      |
| harmful_count    | INTEGER  | ACE feedback: bullet was wrong (default 0)       |

### sessions

Structured handover records submitted via API at end of conversations.

| Column         | Type     | Notes                                         |
|----------------|----------|-----------------------------------------------|
| id             | TEXT PK  | UUID                                          |
| project_id     | TEXT FK  | References projects.id (nullable)             |
| summary        | TEXT     | Brief session summary                         |
| decisions      | TEXT     | JSON array of decision strings                |
| open_items     | TEXT     | JSON array of open item strings               |
| tech_changes   | TEXT     | JSON array of technical changes made          |
| next_steps     | TEXT     | JSON array of next step strings               |
| created_at     | TEXT     | ISO 8601                                      |

### digests

| Column          | Type     | Notes                                        |
|-----------------|----------|----------------------------------------------|
| id              | TEXT PK  | UUID                                         |
| generated_at    | TEXT     | ISO 8601                                     |
| stale_count     | INTEGER  | Number of stale items detected               |
| summary_text    | TEXT     | Full digest content                          |
| sent_telegram   | INTEGER  | 0/1 boolean                                  |
| sent_email      | INTEGER  | 0/1 boolean                                  |

### compile_runs

| Column           | Type     | Notes                                       |
|------------------|----------|---------------------------------------------|
| id               | TEXT PK  | UUID                                        |
| started_at       | TEXT     | ISO 8601                                    |
| completed_at     | TEXT     | ISO 8601 (nullable if failed)               |
| project_slugs    | TEXT     | JSON array of projects compiled             |
| bullets_added    | INTEGER  |                                              |
| bullets_updated  | INTEGER  |                                              |
| bullets_archived | INTEGER  |                                              |
| llm_provider     | TEXT     | "gemini" / "ollama"                         |
| llm_model        | TEXT     | Specific model string                       |
| error            | TEXT     | Error message if failed (nullable)          |

## API Contracts

### Authentication

Bearer token in Authorization header. Token in .env as CONTEXT_ENGINE_TOKEN.
All endpoints require auth except GET /health.

### GET /health

**Response (200):**
```json
{"status": "ok", "version": "1.0.0", "db": "connected", "llm": "gemini"}
```

### POST /sessions

Submit a structured session handover.

**Request:**
```json
{
  "project_slug": "finance-hub",
  "summary": "Completed Task 001 scaffold, started Task 002",
  "decisions": ["Using OpenRouter for categorization"],
  "open_items": ["Task 002 endpoint not yet tested"],
  "tech_changes": ["finance-hub-worker on port 8601"],
  "next_steps": ["Implement /api/categorize endpoint"]
}
```

**Response (201):**
```json
{"id": "uuid", "project_slug": "finance-hub", "created_at": "..."}
```

**Errors:** 404 if project_slug not found, 422 if validation fails.

### GET /projects

**Response (200):**
```json
{
  "projects": [{
    "slug": "finance-hub", "name": "Finance Hub", "status": "active",
    "bullet_count": 24, "stale_count": 2,
    "last_compiled_at": "...", "last_session_at": "..."
  }]
}
```

### POST /projects

Create a new project.

**Request:**
```json
{"name": "Finance Hub", "slug": "finance-hub", "notion_page_id": "optional"}
```

**Response (201):**
```json
{"id": "uuid", "slug": "finance-hub", "status": "active", "created_at": "..."}
```

### GET /projects/{slug}/playbook

Return compiled playbook. Query params: format (markdown|json), categories (comma-separated).

**Response (200, format=markdown):**
```markdown
# Finance Hub — Project Playbook
*Compiled: 2026-03-19T07:00:00Z*

## Current Status
Active — Task 002 in progress

## Open Tasks
- [ ] Task 002: AI categorization (started 2026-03-19)

## Recent Decisions
- Using OpenRouter for categorization (2026-03-19)

## Active Blockers
(none)

## Technical State
- App: gpt-finance-app on port 8600
- Worker: finance-hub-worker on port 8601

## Stale Items (>48h)
(none)

## Next Steps
1. Implement /api/categorize endpoint
```

**Response (200, format=json):** Returns raw bullet array with full metadata.

### POST /compile

Trigger manual compile. Optional body: {"project_slug": "..."} to scope.

**Response (202):**
```json
{"compile_run_id": "uuid", "status": "started", "projects": ["finance-hub"]}
```

### GET /compile/{run_id}

**Response (200):** Compile run record with stats.

### GET /digest/latest

**Response (200):** Most recent digest record.

### POST /bullets/{id}/feedback

**Request:** {"feedback": "helpful"} or {"feedback": "harmful"}
**Response (200):** Updated bullet with counts.

## External Dependencies

```txt
# requirements.txt
fastapi==0.115.12
uvicorn[standard]==0.34.2
aiosqlite==0.21.0
httpx==0.28.1
pydantic==2.11.3
pydantic-settings==2.9.1
python-telegram-bot==22.1
aiosmtplib==3.0.2
google-genai==1.14.0
ollama==0.4.8
jinja2==3.1.6
python-dotenv==1.1.0
pytest==8.3.5
pytest-asyncio==0.25.3
```

## Environment

### Port: 8410
### Domain: context.cp7.dev

### Env vars (.env):
```
CONTEXT_ENGINE_PORT=8410
CONTEXT_ENGINE_TOKEN=<bearer-token>
CONTEXT_ENGINE_DB=./data/context.db
GEMINI_API_KEY=<google-ai-studio-key>
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:1.7b
NOTION_API_TOKEN=<existing-token>
NOTION_TODO_DB=c61ee4e3-cdf1-4f36-a1df-e0053557eb9f
NOTION_SESSION_DB=74a9ce9d-e229-48c3-bc0e-25e409496e4b
LCM_LITE_URL=http://localhost:8400
LCM_LITE_TOKEN=<existing-token>
TELEGRAM_BOT_TOKEN=<existing-shared-token>
TELEGRAM_CHAT_ID=8697133440
GMAIL_ADDRESS=<gmail>
GMAIL_APP_PASSWORD=<app-password>
COMPILE_SCHEDULE=7:00,19:00
STALENESS_THRESHOLD_TASKS=48
STALENESS_THRESHOLD_DECISIONS=168
```

### Systemd units:
- context-engine.service — FastAPI app (user service)
- context-engine-compile.service — One-shot compile runner
- context-engine-compile.timer — Triggers compile 2x daily (7AM, 7PM CT)

## Compile Loop — Detailed Design

### Step 1: Harvest

For each active project:
1. Notion To-Do Tracker — items matching project tag
2. Notion Session Logs — sessions since last compile
3. LCM-Lite — search by project slug, recent sessions
4. Local sessions table — POST /sessions submissions since last compile

Deduplicate by source_id.

### Step 2: Compile (LLM)

Structured prompt to LLM:
```
You are a project state compiler. Given the CURRENT PLAYBOOK (structured bullets)
and NEW RAW DATA (harvested since last compile), produce DELTA UPDATES only.

RULES:
- Output JSON: {"add": [...], "update": [...], "archive": [...]}
- "add": {category, content, source}
- "update": {bullet_id, content}
- "archive": {bullet_id, reason}
- NEVER rewrite the entire playbook
- If new data contradicts existing bullet, UPDATE the existing one
- If a task is completed, ARCHIVE it
- Preserve detail — do NOT compress existing bullets
- Flag items with no recent activity as potentially stale

CURRENT PLAYBOOK:
{current_bullets_json}

NEW RAW DATA:
{harvested_data_json}
```

### Step 3: Apply Deltas

Parse LLM JSON. Insert/update/archive bullets accordingly.

### Step 4: Staleness Scan

- Tasks: stale if > STALENESS_THRESHOLD_TASKS hours
- Decisions: stale if > STALENESS_THRESHOLD_DECISIONS hours
- Blockers: always flagged

### Step 5: Generate Digest

Compile from: stale items, new decisions, completed items, blockers.
- Telegram: short alert if stale_count > 0
- Email: full summary, morning compile only (7AM)

## Bridge Integration

### context_load.sh
```bash
#!/usr/bin/env bash
set -euo pipefail
SLUG="${1:?Usage: context_load.sh <project-slug>}"
TOKEN=$(grep CONTEXT_ENGINE_TOKEN /home/chris/projects/context-engine/.env | cut -d= -f2)
curl -sf -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8410/projects/${SLUG}/playbook?format=markdown"
```

### context_save.sh
```bash
#!/usr/bin/env bash
set -euo pipefail
BODY="${1:?Usage: context_save.sh '<json>'}"
TOKEN=$(grep CONTEXT_ENGINE_TOKEN /home/chris/projects/context-engine/.env | cut -d= -f2)
curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$BODY" "http://localhost:8410/sessions"
```

Both in /home/chris/cp7-bridge/scripts/.

## Constraints

- Claude Code agent: uid=1001 (claude-agent), no sudo, POSIX ACLs on /projects/
- Writable root: /home/chris/projects/context-engine/
- No Docker — systemd user service
- Notion API: internal integration token (existing)
- LCM-Lite: bearer token (existing)
- Gemini Flash free tier: 15 RPM, 1M TPM (sufficient for 2x daily)
- Telegram bot: shared token with OpenClaw
- Gmail SMTP: requires app-specific password (setup needed)
- Bridge scripts: must be in /home/chris/cp7-bridge/scripts/

## Design Decisions Log

| # | Decision | Alternatives | Rationale |
|---|----------|-------------|-----------|
| 1 | SQLite over Postgres | Postgres | Consistent w/ LCM-Lite. No graph needed. Single-file backup. |
| 2 | Systemd over Docker | Docker | Lighter, direct FS access, consistent w/ LCM-Lite. |
| 3 | Gemini Flash primary | Ollama, OpenRouter | Free, fast, great for summarization. Ollama fallback. |
| 4 | ACE bullet structure | Monolithic summaries | Prevents context collapse. Independent updates. No embeddings needed. |
| 5 | 2x daily cron | Event-driven | Simpler, deterministic. Manual trigger available. |
| 6 | Separate from LCM-Lite | Extend LCM-Lite | Different purpose. LCM-Lite is input source, not replaced. |
| 7 | Bearer token auth | API key, mTLS | Consistent w/ LCM-Lite. Tailscale for network security. |
| 8 | Telegram alerts + email summary | Single channel | Telegram immediate + mobile. Email archivable + scannable. |
| 9 | Jinja2 templates | f-strings | Industry standard. Separates content from logic. |
| 10 | httpx | requests, aiohttp | Async-native, modern, consistent API. |


## Review Fixes (Post-Adversarial Review 2026-03-19)

### Fix 1: SQLite Concurrency (Gemini — Plan-Breaking)

**Problem:** Separate compile service + FastAPI app = two processes writing SQLite = `database is locked`.

**Resolution:** Eliminate `context-engine-compile.service` as a standalone Python process. The
systemd timer calls `curl -X POST http://localhost:8410/compile` instead. The compile loop runs
as a FastAPI BackgroundTask inside the single uvicorn process. This ensures one process owns
the SQLite connection.

**Additional:** database.py MUST set these pragmas at connection time:
```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
```

**Updated systemd units:**
- `context-engine.service` — FastAPI app (user service, runs as chris)
- `context-engine-compile.timer` — Triggers `curl -sf -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8410/compile` at 7AM and 7PM CT
- NO separate compile .service — timer runs curl directly via ExecStart=/usr/bin/curl

### Fix 2: LLM Output Validation (DeepSeek — Plan-Breaking)

**Problem:** Raw LLM JSON output has no validation schema.

**Resolution:** Add explicit Pydantic models in models.py:

```python
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
```

compiler.py MUST:
1. Strip markdown fences from LLM output before parsing
2. Parse with `CompileDelta.model_validate_json()`
3. On parse failure: log error, retry once with stricter prompt, then skip compile (don't crash)
4. Validate that all bullet_ids in update/archive exist in DB before applying

### Fix 3: Harvester↔Compiler Data Schema (DeepSeek — Important)

**Resolution:** Define intermediate model:

```python
class HarvestedItem(BaseModel):
    source: Literal["notion_todo", "notion_session", "lcm", "session_handover"]
    source_id: str | None = None
    project_slug: str
    category: str  # best-guess from source
    content: str
    timestamp: str  # ISO 8601
```

Harvesters return `list[HarvestedItem]`. Compiler receives current bullets + harvested items.

### Fix 4: Staleness Thresholds for All Categories

**Updated env vars:**
```
STALENESS_HOURS_TASK=48
STALENESS_HOURS_DECISION=168
STALENESS_HOURS_BLOCKER=0
STALENESS_HOURS_TECH_STATE=168
STALENESS_HOURS_NOTE=336
```

Blockers are ALWAYS flagged (threshold=0). Notes have 14-day threshold.

### Fix 5: LLM Fallback Sequence

llm.py implements:
1. Try Gemini Flash
2. On failure (rate limit, network, error): log warning, try Ollama
3. On Ollama failure: log error, return None (compile skips gracefully)
4. Retry policy: 1 retry per provider with 2s backoff

### Fix 6: Notion Pagination + Rate Limits

harvester/notion.py MUST:
- Handle paginated responses (has_more + start_cursor)
- Respect Notion rate limit (3 req/sec) with 400ms delay between calls
- Cap results at 100 items per harvest to avoid context overflow

### Additional Notes from Review (handled in tasks):
- Bridge scripts: chmod +x in task 008
- .env creation from .env.example: task 002
- data/ directory creation: task 002
- Email/Telegram failure handling: task 007 includes retry logic
- Systemd runs as chris user: task 009

## Updated Design Decisions Log

| # | Decision | Rationale |
|---|----------|-----------|
| 11 | Single-process compile (BackgroundTask) | Prevents SQLite concurrency issues. Timer uses curl. |
| 12 | Strict Pydantic validation for LLM output | Prevents malformed JSON from corrupting state. |
| 13 | HarvestedItem intermediate schema | Clean contract between harvester and compiler. |
| 14 | Per-category staleness thresholds | Different content types have different decay rates. |
