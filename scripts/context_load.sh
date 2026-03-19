#!/usr/bin/env bash
set -euo pipefail
SLUG="${1:?Usage: context_load.sh <project-slug>}"
TOKEN=$(grep CONTEXT_ENGINE_TOKEN /home/chris/projects/context-engine/.env | cut -d= -f2)
curl -sf -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8410/projects/${SLUG}/playbook?format=markdown"
