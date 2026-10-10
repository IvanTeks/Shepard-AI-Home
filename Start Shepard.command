#!/bin/zsh
set -e

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"

if /usr/bin/curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
  /usr/bin/open http://127.0.0.1:8765/
  exit 0
fi

exec /usr/bin/env python3 -m shepard web
