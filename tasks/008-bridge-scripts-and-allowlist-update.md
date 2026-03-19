# Task 008: Bridge scripts and allowlist update

## Objective

Create bridge-accessible scripts for loading playbooks and saving sessions from claude.ai, and add the service to the CP7 Bridge allowlist.

## Context

Tasks 002-007 complete. Full API running.

## Spec Reference

SPEC.md: Bridge Integration section (context_load.sh, context_save.sh).

## Operation Order

1. Write `scripts/context_load.sh` — fetch playbook markdown for a project slug
2. Write `scripts/context_save.sh` — POST session handover JSON
3. Write `scripts/context_compile.sh` — trigger manual compile
4. Write `scripts/context_projects.sh` — list all projects with status
5. chmod +x all scripts
6. Copy scripts to `/home/chris/cp7-bridge/scripts/`
7. Add "context-engine" to bridge service allowlist (if bridge config supports it)

## Deliverables

- [ ] `scripts/context_load.sh` — `Usage: context_load.sh <project-slug>`
- [ ] `scripts/context_save.sh` — `Usage: context_save.sh '<json>'`
- [ ] `scripts/context_compile.sh` — `Usage: context_compile.sh [project-slug]`
- [ ] `scripts/context_projects.sh` — no args, lists projects
- [ ] All scripts copied to `/home/chris/cp7-bridge/scripts/`
- [ ] All scripts are executable (chmod +x)

## Acceptance Criteria

1. [ ] `bash scripts/context_projects.sh` returns JSON project list (after service is running)
2. [ ] `bash scripts/context_load.sh finance-hub` returns markdown playbook
3. [ ] `bash scripts/context_save.sh '{"project_slug":"test","summary":"test session"}'` returns 201
4. [ ] `bash scripts/context_compile.sh` returns 202
5. [ ] All 4 scripts exist in `/home/chris/cp7-bridge/scripts/` and are executable

## Notes

- Scripts read token from .env file: `grep CONTEXT_ENGINE_TOKEN /home/chris/projects/context-engine/.env | cut -d= -f2`
- All scripts use `set -euo pipefail` and `curl -sf`
- context_load.sh should output ONLY the markdown (no curl headers) so bridge run_script returns clean content
- context_save.sh validates that $1 looks like JSON before sending (basic check)
- If bridge allowlist is in a config file, add "context-engine" to it. If it's in Python, note the required change.
