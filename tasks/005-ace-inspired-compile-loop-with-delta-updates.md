# Task 005: ACE-inspired compile loop with delta updates

## Objective

Build the core compile loop: harvest data, send to LLM with structured prompt, parse deltas, apply to database. This is the heart of the system.

## Context

Tasks 002-004 complete. LLM client, harvesters, database, and all models exist.

## Spec Reference

SPEC.md: Compile Loop Steps 1-5, Review Fix 1 (runs as BackgroundTask), Review Fix 2 (output validation), Review Fix 4 (per-category staleness).

## Operation Order

1. Write `src/templates/compile_prompt.md` — full Jinja2 template for the LLM compile prompt. Include the rules from SPEC.md verbatim (NEVER rewrite entire playbook, delta only, preserve detail, flag stale items). Template vars: `current_bullets_json`, `harvested_data_json`, `project_name`.
2. Write `src/compiler.py`:
   - `async def run_compile(project_slug: str | None = None)` — main entry point
   - For each active project (or single project if slug provided):
     a. Get last compile timestamp from compile_runs table
     b. Call `harvest_all(project_slug, since=last_compile_time)`
     c. Load current active bullets for project from DB
     d. Render compile prompt template with current bullets + harvested data
     e. Call `llm_client.compile(prompt)` → get CompileDelta
     f. If CompileDelta is None (LLM failed), log and skip
     g. Apply deltas: INSERT new bullets, UPDATE existing, archive old
     h. Validate all bullet_ids in update/archive exist before applying
     i. Run staleness scan: for each active bullet, check age against category threshold
     j. Update staleness status on bullets exceeding threshold
     k. Record compile_run with stats
   - Return compile_run record
3. Write `tests/test_compiler.py`:
   - Test with pre-populated DB + mock LLM returning valid CompileDelta
   - Test staleness scan marks correct bullets
   - Test invalid bullet_id in update is skipped (not crashed)
   - Test empty harvest data → no changes

## Deliverables

- [ ] `src/templates/compile_prompt.md` — complete Jinja2 template
- [ ] `src/compiler.py` — run_compile() with full harvest→compile→apply→stale loop
- [ ] `tests/test_compiler.py`

## Acceptance Criteria

1. [ ] `python -c "from src.compiler import run_compile; print('Compiler OK')"`
2. [ ] `pytest tests/test_compiler.py -v` — all tests pass
3. [ ] Test: mock LLM returns add/update/archive → DB reflects changes correctly
4. [ ] Test: bullet older than staleness threshold → status set to "stale"
5. [ ] Test: invalid bullet_id in update array → skipped with warning, no crash

## Notes

- Compile runs inside the FastAPI process as BackgroundTask (Review Fix 1)
- Use `asyncio.Lock()` to prevent concurrent compiles
- Jinja2 template loaded from src/templates/ at startup
- The compile prompt must instruct the LLM to output ONLY JSON, no markdown, no explanation
- If harvested data is empty AND no stale bullets, skip LLM call entirely (save API quota)
