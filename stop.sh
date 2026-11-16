#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ -f .mia-pids ]]; then
  while read -r pid; do kill "$pid" 2>/dev/null || true; done < .mia-pids
  rm -f .mia-pids
else
  echo "No standalone MIA PID file found. Use Ctrl+C in the start.sh terminal to stop its servers."
fi
