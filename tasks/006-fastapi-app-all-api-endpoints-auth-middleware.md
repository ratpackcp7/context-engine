# Task 006: FastAPI app, all API endpoints, auth middleware

## Objective

Build the FastAPI application with all API endpoints, bearer token auth middleware, and lifespan handler.

## Context

Tasks 002-005 complete. Database, models, LLM client, harvesters, and compiler all exist.

## Spec Reference

SPEC.md: API Contracts (all endpoints), Authentication section, Review Fix 1 (compile as BackgroundTask).

## Operation Order

1. Write `src/main.py`:
   - FastAPI app with lifespan handler: init_db on startup
   - Auth dependency: verify Bearer token from Authorization header against config
   - Include all API routers
   - GET /health (no auth required) → HealthResponse
2. Write `src/api/sessions.py`:
   - POST /sessions → validate SessionCreate, resolve project_slug to project_id, insert session, return SessionResponse
   - Convert session fields (decisions, open_items, tech_changes, next_steps) into queued bullets for next compile
3. Write `src/api/projects.py`:
   - GET /projects → list all projects with bullet_count, stale_count, last_compiled_at, last_session_at
   - POST /projects → create project from ProjectCreate
   - GET /projects/{slug}/playbook → render compiled playbook in markdown or JSON format
   - Support query params: format (markdown|json), categories (comma-separated filter)
   - Markdown format: structured template matching SPEC.md example output
4. Write `src/api/compile.py`:
   - POST /compile → start compile as BackgroundTask, return 202 with compile_run_id
   - GET /compile/{run_id} → return compile run status/stats
5. Write `src/api/digest.py`:
   - GET /digest/latest → return most recent digest record
6. Add POST /bullets/{id}/feedback endpoint (in projects.py or separate)
7. Write `tests/test_api.py` — test all endpoints with TestClient

## Deliverables

- [ ] `src/main.py` — FastAPI app, lifespan, auth dependency, router includes
- [ ] `src/api/sessions.py` — POST /sessions
- [ ] `src/api/projects.py` — GET /projects, POST /projects, GET /projects/{slug}/playbook, POST /bullets/{id}/feedback
- [ ] `src/api/compile.py` — POST /compile, GET /compile/{run_id}
- [ ] `src/api/digest.py` — GET /digest/latest
- [ ] `tests/test_api.py`

## Acceptance Criteria

1. [ ] `source venv/bin/activate && uvicorn src.main:app --port 8410` starts without errors
2. [ ] `curl -s http://localhost:8410/health` returns 200 with status "ok"
3. [ ] `curl -s http://localhost:8410/projects` returns 401 (no auth)
4. [ ] `curl -s -H "Authorization: Bearer testtoken" http://localhost:8410/projects` returns 200
5. [ ] `pytest tests/test_api.py -v` — all tests pass
6. [ ] POST /projects creates a project, GET /projects lists it
7. [ ] POST /sessions with valid project_slug returns 201
8. [ ] GET /projects/{slug}/playbook returns markdown-formatted playbook

## Notes

- Auth: simple bearer token check, NOT OAuth. Compare against config.token.
- GET /health is the ONLY unauthenticated endpoint
- Playbook markdown format must match SPEC.md example exactly (sections: Status, Open Tasks, Recent Decisions, Active Blockers, Technical State, Stale Items, Next Steps)
- Use `fastapi.BackgroundTasks` for compile trigger
- For testing, use a .env.test or override config with test values
