# Context Engine — Agent Context

## Project Overview
A FastAPI service on acerserver that compiles scattered session state (Notion, LCM-Lite, manual handovers) into per-project "playbooks" using ACE-inspired structured bullets, and pushes daily digests via Telegram + email.

## Working Directory
`/home/chris/projects/context-engine/`

## Key Constraints
- You are running as `claude-agent` (uid=1001). Files in this project have been chmod'd for your access.
- Python venv at `./venv/` — always `source venv/bin/activate` before running Python.
- SQLite DB at `./data/context.db` — single-process access only (WAL mode + busy_timeout).
- No Docker — this runs as a systemd user service.
- Port 8410 on localhost.

## Critical Design Rules
1. **Single process owns SQLite.** The compile loop runs as a FastAPI BackgroundTask, NOT a separate process.
2. **Delta updates only.** The compiler NEVER rewrites the full playbook. It produces add/update/archive deltas.
3. **Strict LLM output validation.** Always parse LLM output through CompileDelta Pydantic model. Strip markdown fences first.
4. **Gemini Flash primary, Ollama fallback.** Try Gemini first, fall back to Ollama on failure.
5. **All timestamps ISO 8601 UTC.**
6. **staleness_days is computed on read**, not stored.

## Existing Infrastructure
- Notion API token: works, existing integration
- LCM-Lite: running on localhost:8400 with bearer auth
- Ollama: running on localhost:11434
- Telegram bot: shared token with OpenClaw (chat ID: 8697133440)
- CP7 Bridge scripts dir: `/home/chris/cp7-bridge/scripts/`

## After Each Task
1. Write your report to `.playbook-report.md`
2. `git add -A && git commit -m 'task NNN: description'`
