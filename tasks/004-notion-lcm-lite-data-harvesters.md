# Task 004: Notion + LCM-Lite data harvesters

## Objective

Build harvesters that pull raw data from Notion (To-Do Tracker + Session Logs) and LCM-Lite, returning structured HarvestedItem lists.

## Context

Tasks 002-003 complete. Models (HarvestedItem), config, and database exist.

## Spec Reference

SPEC.md: Compile Loop Step 1 (Harvest), Review Fix 3 (HarvestedItem schema), Review Fix 6 (Notion pagination).

## Operation Order

1. Write `src/harvester/notion.py`:
   - `harvest_todos(project_slug, since)` → queries Notion To-Do Tracker DB (datasource c61ee4e3-cdf1-4f36-a1df-e0053557eb9f) via Notion API
   - `harvest_sessions(project_slug, since)` → queries Session Logs DB (datasource 74a9ce9d-e229-48c3-bc0e-25e409496e4b)
   - Handle pagination (has_more + start_cursor loop)
   - Respect rate limit: 400ms delay between requests
   - Cap at 100 items per harvest
   - Return list[HarvestedItem]
2. Write `src/harvester/lcm.py`:
   - `harvest_lcm(project_slug, since)` → GET LCM-Lite /search?q={project_slug}&limit=10
   - Parse results into list[HarvestedItem]
3. Write `src/harvester/__init__.py` with `harvest_all(project_slug, since)` that calls all three and deduplicates by source_id
4. Write `tests/test_harvester.py` with mocked HTTP responses

## Deliverables

- [ ] `src/harvester/notion.py` — harvest_todos(), harvest_sessions()
- [ ] `src/harvester/lcm.py` — harvest_lcm()
- [ ] `src/harvester/__init__.py` — harvest_all() with dedup
- [ ] `tests/test_harvester.py`

## Acceptance Criteria

1. [ ] `python -c "from src.harvester import harvest_all; print('Harvester OK')"`
2. [ ] `pytest tests/test_harvester.py -v` — all tests pass
3. [ ] Mock test: Notion pagination with 2 pages returns combined results
4. [ ] Mock test: duplicate source_ids are deduplicated

## Notes

- Notion API: POST https://api.notion.com/v1/databases/{db_id}/query with filter and sorts
- Notion API version header: `Notion-Version: 2022-06-28`
- Auth: `Authorization: Bearer {notion_token}`
- LCM-Lite: GET http://localhost:8400/search?q=... with `Authorization: Bearer {lcm_token}`
- `since` parameter is ISO 8601 string — filter Notion by last_edited_time, LCM by timestamp
- Web search Notion API query database docs before implementing
