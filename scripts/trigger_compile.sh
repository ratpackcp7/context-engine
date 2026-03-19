#!/usr/bin/env bash
set -euo pipefail
# Trigger a compile run via the Context Engine API
# Called by context-engine-compile.timer via context-engine-compile.service

ENV_FILE="/home/chris/projects/context-engine/.env"
TOKEN=$(grep '^CONTEXT_ENGINE_TOKEN=' "$ENV_FILE" | cut -d= -f2)

curl -sf -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  http://localhost:8410/compile
