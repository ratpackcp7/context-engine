# Spec Review — DeepSeek V3.2 (Practitioner)

**Model:** deepseek/deepseek-chat
**Date:** 2026-03-19
**Input tokens:** ~3090
**Estimated cost:** $0.0106

---

1. **Missing Error Handling for LLM Abstraction:**
   - **Issue:** The spec does not detail error handling for LLM API failures (e.g., Gemini Flash rate limits, Ollama unavailability).
   - **Why it matters:** Without robust error handling, the system could crash or silently fail during LLM API calls.
   - **Fix:** Add detailed error handling in `llm.py`, including retries, fallback logic, and logging.

2. **Ambiguous Notion API Token Usage:**
   - **Issue:** The spec mentions `NOTION_API_TOKEN` but does not specify if it’s for reading or writing, nor if it handles pagination or rate limits.
   - **Why it matters:** The agent might assume token has read/write access or fail to handle large datasets.
   - **Fix:** Clarify token permissions in `.env.example` and add pagination/rate limit handling in `notion.py`.

3. **Undefined JSON Schema for LLM Compile Output:**
   - **Issue:** The `compile_prompt.md` template specifies LLM output as `{"add": [...], "update": [...], "archive": [...]}` but lacks detailed schema.
   - **Why it matters:** The LLM might produce malformed JSON, causing runtime errors.
   - **Fix:** Define a strict JSON schema in `models.py` and validate LLM output against it.

4. **Missing Staleness Thresholds for All Categories:**
   - **Issue:** The spec defines `STALENESS_THRESHOLD_TASKS` and `STALENESS_THRESHOLD_DECISIONS` but not for other categories like `blockers` or `tech_state`.
   - **Why it matters:** Without thresholds, staleness scans for other categories will fail or behave unpredictably.
   - **Fix:** Add thresholds for all categories in `.env.example` and `config.py`.

5. **Unspecified Rate Limits for Telegram Alerts:**
   - **Issue:** The spec does not mention Telegram rate limits or handling for failed message sends.
   - **Why it matters:** Frequent alerts could hit rate limits, causing message failures.
   - **Fix:** Add rate limit handling and retry logic in `digest.py`.

6. **Undefined Email Template Data:**
   - **Issue:** The `digest_email.html` template is mentioned but lacks details on required variables or structure.
   - **Why it matters:** The agent might produce a malformed HTML email or miss key data.
   - **Fix:** Define a Jinja2 template with required variables and example data in `templates/`.

7. **Missing Dependency Order in Task Breakdown:**
   - **Issue:** The task breakdown does not specify that `006 FastAPI app` depends on `002 Project scaffold`, `003 LLM abstraction`, etc.
   - **Why it matters:** The agent might attempt to build the API before dependencies are ready.
   - **Fix:** Update the task breakdown to reflect dependencies explicitly.

8. **Undefined Backup Strategy for SQLite DB:**
   - **Issue:** The spec mentions SQLite backups but does not detail the strategy (e.g., frequency, location, rotation).
   - **Why it matters:** Data could be lost if the DB file gets corrupted or deleted.
   - **Fix:** Add a backup strategy in `database.py` or `.env.example`.

9. **Unclear Handling of Systemd Service Failures:**
   - **Issue:** The spec does not specify how failures in `context-engine-compile.service` are handled or logged.
   - **Why it matters:** Failed compiles could go unnoticed, leading to stale project state.
   - **Fix:** Add error handling and logging in the Systemd service unit file.

10. **Missing Validation for POST /sessions Request:**
   - **Issue:** The spec lacks detailed validation rules for the JSON body in `POST /sessions`.
   - **Why it matters:** Invalid or malformed requests could corrupt the sessions table.
   - **Fix:** Define strict validation rules in `models.py`.

11. **Undefined ACLs for Bridge Scripts:**
   - **Issue:** The spec mentions POSIX ACLs but does not specify permissions for `context_load.sh` and `context_save.sh`.
   - **Why it matters:** Insufficient permissions could block access to the API.
   - **Fix:** Define required ACLs in the task notes.

12. **Unspecified Error Handling for SMTP Failures:**
   - **Issue:** The spec does not detail how SMTP failures (e.g., incorrect app password) are handled.
   - **Why it matters:** Failed email sends could go unnoticed, causing communication gaps.
   - **Fix:** Add error handling and retry logic in `digest.py`.

13. **Missing LLM Fallback Sequence:**
   - **Issue:** The spec does not define the sequence of LLM fallbacks if Gemini Flash fails.
   - **Why it matters:** The system might not properly fall back to Ollama or other LLMs.
   - **Fix:** Define the fallback sequence in `llm.py`.

14. **Undefined Bulk API Rate Limits:**
   - **Issue:** The spec does not address rate limits for bulk API calls (e.g., harvesting multiple projects).
   - **Why it matters:** Bulk operations could hit rate limits, causing failures.
   - **Fix:** Add rate limit handling in `harvester/notion.py` and `harvester/lcm.py`.

15. **Unspecified Staleness Scan Frequency:**
   - **Issue:** The spec does not specify how often staleness scans occur beyond the compile schedule.
   - **Why it matters:** Staleness scans might not align with compile cycles, leading to outdated alerts.
   - **Fix:** Clarify staleness scan frequency in the design notes.

16. **Missing Testing for Compile Loop:**
   - **Issue:** The spec mentions smoke tests but does not specify unit or integration tests for the compile loop.
   - **Why it matters:** The compile loop might produce incorrect deltas without proper testing.
   - **Fix:** Add detailed test cases in `tests/test_compiler.py`.

17. **Undefined Telemetry or Monitoring:**
   - **Issue:** The spec does not mention logging, monitoring, or telemetry for the service.
   - **Why it matters:** Issues might go unnoticed without proper monitoring.
   - **Fix:** Add logging and monitoring setup in `main.py` and systemd unit files.

18. **Ambiguous Interface Between Harvester and Compiler:**
   - **Issue:** The spec does not define the data format passed from harvester to compiler.
   - **Why it matters:** Mismatched data formats could cause runtime errors.
   - **Fix:** Define the data schema in `models.py`.

19. **Unspecified API Throttling:**
   - **Issue:** The spec does not mention API throttling or rate limiting for endpoints.
   - **Why it matters:** Excessive API calls could overwhelm the service.
   - **Fix:** Add throttling middleware in `main.py`.

20. **Missing Documentation for ACE Feedback Mechanism:**
   - **Issue:** The spec does not detail how feedback (`helpful_count`, `harmful_count`) is collected or used.
   - **Why it matters:** Feedback collection might not work as intended.
   - **Fix:** Document the feedback mechanism in `AGENT_CONTEXT.md`.
