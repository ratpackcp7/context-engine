# Spec Review — Gemini 3.1 Pro (Architect)

**Model:** google/gemini-3.1-pro-preview
**Date:** 2026-03-19
**Input tokens:** ~3090
**Estimated cost:** $0.0106

---

This specification is filled with hidden traps, unresolved dependencies, and architectural contradictions that will cause an autonomous agent to fail catastrophically. Claude Code follows literal text and will not assume missing logical links. 

Here is the brutal review of every issue that will break the agent, stall the process, or crash the application.

### 1. SQLite Concurrency & Deadlocks
* **What's wrong:** You have a persistent FastAPI app (`context-engine.service`) AND a separate execution script for the compiler (`context-engine-compile.service`). Both will attempt to read/write to standard SQLite concurrently.
* **Why it matters:** Standard SQLite does not handle concurrent Python processes writing at the same time. The first time a background compile runs while a user is saving a session handover, `aiosqlite` will instantly throw `sqlite3.OperationalError: database is locked` and crash the system. 
* **How to fix it:** Delete the `context-engine-compile.service` python script altogether. Instead, have the systemd timer (`context-engine-compile.timer`) execute a one-shot `curl -X POST http://localhost:8410/compile`. Let FastAPI's `BackgroundTasks` handle the compilation. This ensures a single parent process (uvicorn) manages the SQLite connection. Furthermore, instruct the agent to enable `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;` on startup.

### 2. The Task
