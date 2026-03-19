#!/usr/bin/env bash
set -euo pipefail
TOKEN=$(grep CONTEXT_ENGINE_TOKEN /home/chris/projects/context-engine/.env | cut -d= -f2)
curl -sf -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8410/projects"
