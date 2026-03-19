# Task 009: Systemd service, timer, Cloudflare tunnel

## Objective

Deploy the Context Engine as a systemd user service, configure the compile timer, and add Cloudflare tunnel route.

## Context

Tasks 002-008 complete. App works, scripts work, ready for production deployment.

## Spec Reference

SPEC.md: Environment (systemd units), Review Fix 1 (timer uses curl, not separate Python process).

## Operation Order

1. Create `.env` from `.env.example` with real values:
   - Generate CONTEXT_ENGINE_TOKEN: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
   - GEMINI_API_KEY: read from existing key store or prompt user
   - NOTION_API_TOKEN: read from existing config
   - LCM_LITE_TOKEN: read from /home/chris/lcm-lite/.env
   - TELEGRAM_BOT_TOKEN: read from /home/chris/.openclaw/.env
   - GMAIL_ADDRESS + GMAIL_APP_PASSWORD: will need user input (note in report)
2. Write `context-engine.service` systemd user unit:
   - User service (installed to ~/.config/systemd/user/)
   - ExecStart: `/home/chris/projects/context-engine/venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8410`
   - WorkingDirectory: /home/chris/projects/context-engine
   - EnvironmentFile: /home/chris/projects/context-engine/.env
   - Restart=on-failure, RestartSec=5
3. Write `context-engine-compile.timer` systemd user timer:
   - OnCalendar=*-*-* 07:00:00 and *-*-* 19:00:00 (America/Chicago timezone)
   - Triggers a companion .service that runs curl
4. Write `context-engine-compile.service` — one-shot:
   - ExecStart=/usr/bin/curl -sf -X POST -H "Authorization: Bearer ${TOKEN}" http://localhost:8410/compile
   - Read TOKEN from .env
   - Type=oneshot
5. Install, enable, and start:
   - `systemctl --user daemon-reload`
   - `systemctl --user enable --now context-engine.service`
   - `systemctl --user enable --now context-engine-compile.timer`
6. Add Cloudflare tunnel route:
   - Run: `bash /home/chris/cp7-bridge/scripts/cf-tunnel.sh add context localhost:8410`
   - This adds context.cp7.dev → localhost:8410

## Deliverables

- [ ] `.env` — populated with real tokens (except Gmail which needs user input)
- [ ] `context-engine.service` installed in `~/.config/systemd/user/`
- [ ] `context-engine-compile.timer` installed in `~/.config/systemd/user/`
- [ ] `context-engine-compile.service` installed in `~/.config/systemd/user/`
- [ ] Service running on port 8410
- [ ] Timer active for 7AM/7PM CT
- [ ] Cloudflare tunnel route added for context.cp7.dev

## Acceptance Criteria

1. [ ] `systemctl --user status context-engine` shows active (running)
2. [ ] `curl -s http://localhost:8410/health` returns 200
3. [ ] `systemctl --user list-timers` shows context-engine-compile.timer with next trigger
4. [ ] `curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8410/projects` returns 200
5. [ ] Cloudflare tunnel route for context.cp7.dev exists

## Notes

- Runs as chris user (NOT claude-agent) — needs access to .env and data/
- For the timer's curl command, read token from .env file: use a wrapper script or Environment= directive
- Timer uses America/Chicago timezone — set via `TZ=America/Chicago` in timer's Environment
- Cloudflare tunnel script: cf-tunnel.sh add <subdomain> <origin>
- If Gmail credentials unavailable, note in report — email digest will be disabled until configured
- The compile timer's companion service is a SIMPLE curl wrapper, NOT a Python process (Review Fix 1)
