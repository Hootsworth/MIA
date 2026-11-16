#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then echo "Python 3.12+ is required (set PYTHON to its executable)." >&2; exit 1; fi
PY_VERSION="$($PYTHON -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VERSION%%.*}"; PY_MINOR="${PY_VERSION#*.}"
if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 12) )); then echo "Python 3.12+ is required; found $PY_VERSION (set PYTHON to a suitable executable)." >&2; exit 1; fi
if ! command -v node >/dev/null 2>&1; then echo "Node.js LTS is required." >&2; exit 1; fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if (( NODE_MAJOR < 20 )); then echo "Node.js 20 or newer is required; found $(node --version)." >&2; exit 1; fi

export PYTORCH_ENABLE_MPS_FALLBACK=1
MODEL_CACHE="${MIA_MODEL_CACHE:-storage/models}"
if [[ "$MODEL_CACHE" = /* ]]; then export HF_HOME="$MODEL_CACHE"; else export HF_HOME="$ROOT/$MODEL_CACHE"; fi
SIMILARITY_INDEX="${MIA_SIMILARITY_INDEX:-storage/similarity/index.sqlite3}"
if [[ "$SIMILARITY_INDEX" = /* ]]; then export MIA_SIMILARITY_INDEX="$SIMILARITY_INDEX"; else export MIA_SIMILARITY_INDEX="$ROOT/$SIMILARITY_INDEX"; fi
mkdir -p data storage/documents storage/reports storage/exports storage/logs
mkdir -p "$HF_HOME"
mkdir -p "$(dirname "$MIA_SIMILARITY_INDEX")"
if [[ ! -d .venv ]]; then "$PYTHON" -m venv .venv; fi
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps ./packages/mia-detect
if [[ ! -d frontend/node_modules ]]; then (cd frontend && npm install); fi

.venv/bin/python -c 'from backend.core.database import init_db; init_db()'
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 >storage/logs/backend.log 2>&1 &
BACKEND_PID=$!
(cd frontend && exec ./node_modules/.bin/next dev --hostname 0.0.0.0) >"$ROOT/storage/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
cleanup() {
  trap - INT TERM EXIT
  terminate_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2>/dev/null || true); do
      terminate_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
  }
  terminate_tree "$FRONTEND_PID"
  terminate_tree "$BACKEND_PID"
  wait "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
  rm -f .mia-pids
}
printf '%s\n%s\n' "$BACKEND_PID" "$FRONTEND_PID" > .mia-pids
trap cleanup INT TERM EXIT
echo "MIA is starting. Frontend: http://localhost:3000 | Backend: http://localhost:8000 | API docs: http://localhost:8000/docs"
while [[ -f .mia-pids ]] && kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do sleep 1; done
if [[ ! -f .mia-pids ]]; then exit 0; fi
echo "A MIA server stopped. Check storage/logs/ for details." >&2
exit 1
