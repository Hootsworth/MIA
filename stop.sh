#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ -f .mia-pids ]]; then
  terminate_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2>/dev/null || true); do
      terminate_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
  }
  while read -r pid; do
    [[ -n "$pid" ]] && terminate_tree "$pid"
  done < .mia-pids
  rm -f .mia-pids
  echo "Stopped MIA servers."
else
  echo "No standalone MIA PID file found. Use Ctrl+C in the start.sh terminal to stop its servers."
fi
