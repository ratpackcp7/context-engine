#!/usr/bin/env bash
set -euo pipefail
BODY="${1:?Usage: context_save.sh '<json>'}"
# Basic JSON validation
if [[ "$BODY" != \{* ]]; then
  echo "Error: argument must be a JSON object starting with {" >&2
  exit 1
fi
TOKEN=$(grep CONTEXT_ENGINE_TOKEN /home/chris/projects/context-engine/.env | cut -d= -f2)
curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$BODY" "http://localhost:8410/sessions"
