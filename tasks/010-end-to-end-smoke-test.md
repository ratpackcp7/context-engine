# Task 010: End-to-end smoke test

## Objective

Run a complete end-to-end test: create a project, submit a session, trigger compile, verify playbook output, verify digest.

## Context

Tasks 002-009 complete. Service is deployed and running.

## Spec Reference

All of SPEC.md — this validates the entire system.

## Operation Order

1. Write `tests/test_e2e.py` — end-to-end test script that:
   a. GET /health → verify 200
   b. POST /projects → create "test-project"
   c. POST /sessions → submit test session with decisions, open_items, tech_changes, next_steps
   d. POST /compile → trigger compile (with project_slug="test-project")
   e. Wait 10s for BackgroundTask to complete
   f. GET /compile/{run_id} → verify status=completed, bullets_added > 0
   g. GET /projects/test-project/playbook?format=markdown → verify markdown contains expected sections
   h. GET /projects/test-project/playbook?format=json → verify JSON has bullets array
   i. GET /projects → verify test-project listed with bullet_count > 0
   j. POST /bullets/{id}/feedback → submit "helpful" feedback, verify count incremented
   k. GET /digest/latest → verify digest exists (may be empty if no stale items)

2. Run the E2E test against running service:
   ```
   source venv/bin/activate
   CONTEXT_ENGINE_URL=http://localhost:8410 CONTEXT_ENGINE_TOKEN=<token> pytest tests/test_e2e.py -v
   ```

3. Test bridge scripts:
   - `bash /home/chris/cp7-bridge/scripts/context_projects.sh` → returns project list
   - `bash /home/chris/cp7-bridge/scripts/context_load.sh test-project` → returns playbook markdown
   - `bash /home/chris/cp7-bridge/scripts/context_compile.sh test-project` → returns 202

4. Seed initial projects matching Chris's active work:
   ```
   curl -X POST ... '{"name": "Finance Hub", "slug": "finance-hub", "notion_page_id": "31ff6863-72de-81c1"}'
   curl -X POST ... '{"name": "CBA Negotiations", "slug": "cba"}'
   curl -X POST ... '{"name": "Context Engine", "slug": "context-engine"}'
   curl -X POST ... '{"name": "Homelab Ops", "slug": "homelab"}'
   curl -X POST ... '{"name": "MFD Roster", "slug": "mfd-roster"}'
   ```

5. Trigger a full compile to seed initial bullets from Notion + LCM-Lite:
   ```
   curl -X POST ... http://localhost:8410/compile
   ```

6. Write summary report in `.playbook-report.md`

## Deliverables

- [ ] `tests/test_e2e.py` — full E2E test
- [ ] 5 projects seeded in database
- [ ] Initial compile run completed
- [ ] Bridge scripts verified working

## Acceptance Criteria

1. [ ] `pytest tests/test_e2e.py -v` — all tests pass against running service
2. [ ] `context_load.sh finance-hub` returns non-empty markdown playbook
3. [ ] `context_projects.sh` lists all 5 seeded projects
4. [ ] Initial compile shows bullets_added > 0 (data pulled from Notion/LCM-Lite)
5. [ ] Service is stable after full test run (no crashes in journal)

## Notes

- E2E tests hit the REAL running service (not mocked)
- Use httpx or requests in test, not FastAPI TestClient
- Token must be passed via env var or read from .env
- If Notion/LCM harvesting returns no data on initial compile (empty DBs), that's OK — test session data should still produce bullets
- Clean up test-project after E2E tests pass (DELETE if endpoint exists, or leave — it won't hurt)
- After seeding projects, the system is LIVE and ready for production use
