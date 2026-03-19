#!/usr/bin/env bash
set -euo pipefail
TOKEN=$(grep CONTEXT_ENGINE_TOKEN /home/chris/projects/context-engine/.env | cut -d= -f2)
if [ $# -gt 0 ]; then
  curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"project_slug\":\"$1\"}" "http://localhost:8410/compile"
else
  curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
    "http://localhost:8410/compile"
fi
