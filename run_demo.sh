#!/usr/bin/env bash
#
# SkunkLabs MVP V0 - single-command launcher.
#
# Starts the backend and the operator UI, waits for both to be healthy, and
# opens the screen. Ctrl-C stops everything.
#
#   ./run_demo.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

VENV="$REPO_ROOT/.venv"
PYTHON="$VENV/bin/python"
BACKEND_PORT="${SKUNK_PORT:-8000}"
FRONTEND_PORT=5173

log()  { printf '\033[38;5;173m[skunklabs]\033[0m %s\n' "$*"; }
fail() { printf '\033[38;5;167m[skunklabs]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
[ -x "$PYTHON" ] || fail "No virtualenv at .venv - run:  python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt"

"$PYTHON" -c "import fastapi, cv2" 2>/dev/null \
  || fail "Backend dependencies missing - run:  .venv/bin/pip install -r requirements.txt"

[ -d "$REPO_ROOT/frontend/node_modules" ] \
  || fail "Frontend dependencies missing - run:  cd frontend && npm install"

# The launcher demo needs no video. The sensor lab's demo clip is generated,
# not committed - create it on first run, only when the video pipeline is on.
VIDEO="${SKUNK_VIDEO_PATH:-$REPO_ROOT/assets/videos/demo_drone.mp4}"
if [ "${SKUNK_VIDEO_PIPELINE_ENABLED:-false}" = "true" ] \
  && [ "${SKUNK_VIDEO_SOURCE:-file}" = "file" ] && [ ! -f "$VIDEO" ]; then
  log "Demo clip missing - generating it (about 10 seconds)…"
  "$PYTHON" scripts/make_demo_video.py
fi

# ---------------------------------------------------------------- teardown
PIDS=()
cleanup() {
  log "Shutting down…"
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------- backend
log "Starting backend on http://127.0.0.1:${BACKEND_PORT}"
"$PYTHON" -m backend.main &
PIDS+=($!)

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1 \
  || fail "Backend did not become healthy. Check the log output above."
log "Backend healthy."

# ---------------------------------------------------------------- frontend
log "Starting operator UI on http://localhost:${FRONTEND_PORT}"
( cd "$REPO_ROOT/frontend" && npm run dev -- --port "$FRONTEND_PORT" ) &
PIDS+=($!)

for _ in $(seq 1 60); do
  if curl -sf "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

log "Operator interface: http://localhost:${FRONTEND_PORT}/map"
command -v open >/dev/null && open "http://localhost:${FRONTEND_PORT}/map" || true

log "Ready. Press Ctrl-C to stop."
wait
