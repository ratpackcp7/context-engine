# Task 007: Telegram alerts + email summary digest

## Objective

Build the digest system: generate summaries from compiled state, send Telegram alerts for stale items, send email daily summary.

## Context

Tasks 002-006 complete. Full API, compiler, and database exist.

## Spec Reference

SPEC.md: Compile Loop Step 5 (Generate Digest), Environment (Telegram/Email config).

## Operation Order

1. Write `src/templates/digest_telegram.md` — Jinja2 template for Telegram message:
   - Compact format (Telegram has 4096 char limit)
   - Show: stale item count, list of stale items (project + content), new blockers
   - Example: "⚠️ 3 stale items:\n• Finance Hub: Task 002 AI categorization (3d)\n• CBA: Longevity cost model (5d)\n📋 0 new blockers"
2. Write `src/templates/digest_email.html` — Jinja2 HTML template for email:
   - Per-project sections with: status, open tasks, stale items, recent decisions, next steps
   - Clean, readable HTML (inline CSS for email compatibility)
   - Subject line template: "CP7 Context Digest — {date} — {stale_count} stale items"
3. Write `src/digest.py`:
   - `async def generate_digest()` → query all active projects, count stale bullets, build digest text
   - `async def send_telegram(digest_text)` → use python-telegram-bot to send to TELEGRAM_CHAT_ID
   - `async def send_email(subject, html_body)` → use aiosmtplib to send via Gmail SMTP
   - `async def run_digest(morning: bool = False)`:
     - Generate digest
     - If stale_count > 0: always send Telegram alert
     - If morning=True: always send email summary (even if nothing stale)
     - Record digest in digests table
   - Error handling: if Telegram send fails, log error, still try email (and vice versa). Never crash.
4. Write `tests/test_digest.py` — mock Telegram/SMTP, test template rendering, test send failure handling

## Deliverables

- [ ] `src/templates/digest_telegram.md` — Telegram Jinja2 template
- [ ] `src/templates/digest_email.html` — Email HTML Jinja2 template
- [ ] `src/digest.py` — generate_digest(), send_telegram(), send_email(), run_digest()
- [ ] `tests/test_digest.py`

## Acceptance Criteria

1. [ ] `python -c "from src.digest import generate_digest, run_digest; print('Digest OK')"`
2. [ ] `pytest tests/test_digest.py -v` — all tests pass
3. [ ] Template renders correctly with test data (stale items, no stale items, multiple projects)
4. [ ] Mock test: Telegram failure doesn't prevent email send
5. [ ] Mock test: digest record saved to DB even if both sends fail

## Notes

- python-telegram-bot async: `bot = telegram.Bot(token=...); await bot.send_message(chat_id=..., text=..., parse_mode='Markdown')`
- aiosmtplib: `await aiosmtplib.send(message, hostname='smtp.gmail.com', port=587, start_tls=True, username=..., password=...)`
- Gmail SMTP requires app-specific password (not regular password)
- Telegram Markdown: use *bold*, _italic_, `code` formatting
- Truncate Telegram message to 4096 chars if needed
- Email from address: use GMAIL_ADDRESS from config
