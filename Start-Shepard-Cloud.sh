#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p .runtime

if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
  echo "Shepard is already awake: http://127.0.0.1:8765/"
  exit 0
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "Shepard will open, but AI jobs need a Codespaces secret named GEMINI_API_KEY."
fi

export SHEPARD_HOST="${SHEPARD_HOST:-0.0.0.0}"
export SHEPARD_MODEL_OVERRIDE="${SHEPARD_MODEL_OVERRIDE:-gemini:gemini-3.8-flash}"

nohup python3 -m shepard web --host "$SHEPARD_HOST" --port 8765 --no-open \
  > .runtime/shepard-cloud.log 2>&1 &
echo $! > .runtime/shepard-cloud.pid

for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
    echo "Shepard Cloud Home is awake: http://127.0.0.1:8765/"
    exit 0
  fi
  sleep 1
done

echo "Shepard did not start. Read .runtime/shepard-cloud.log for the error." >&2
exit 1
