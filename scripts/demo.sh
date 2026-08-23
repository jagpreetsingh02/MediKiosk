#!/usr/bin/env bash
# One command to run the whole thing. `./scripts/demo.sh`
#
# Starts the API and the frontend, waits for both, and prints the two URLs. No Docker
# required: the default configuration is SQLite plus the in-process session store, so this
# works on a laptop with no containers and no network.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [ ! -d .venv ]; then
  echo "No .venv found. Run:  python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt"
  exit 1
fi

cleanup() {
  echo ""
  echo "Stopping…"
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  [ -n "${WEB_PID:-}" ] && kill "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting the API on :8000…"
PYTHONPATH="$ROOT" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  > /tmp/medikiosk-api.log 2>&1 &
API_PID=$!

for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8000/health > /dev/null 2>&1; then break; fi
  sleep 0.25
done

if ! curl -fsS http://127.0.0.1:8000/health > /dev/null 2>&1; then
  echo "The API did not start. Last 30 lines of /tmp/medikiosk-api.log:"
  tail -30 /tmp/medikiosk-api.log
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend dependencies…"
  (cd frontend && npm install --silent)
fi

echo "Starting the frontend on :5173…"
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) > /tmp/medikiosk-web.log 2>&1 &
WEB_PID=$!

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:5173 > /dev/null 2>&1; then break; fi
  sleep 0.25
done

cat <<BANNER

  ────────────────────────────────────────────────────────────────
   MediKiosk is running

     Kiosk (patient)       http://127.0.0.1:5173/
     Physician review      http://127.0.0.1:5173/physician
     API docs              http://127.0.0.1:8000/docs
     What is mocked        http://127.0.0.1:8000/about

   Demo login
     Patient   any listed ABHA address, OTP 123456
     Staff     any name, role "clinician"

   The frontend hot-reloads. The API does NOT — restart this script after a
   Python change, or use `make api` (which runs uvicorn --reload) while editing.

   Logs: /tmp/medikiosk-api.log  /tmp/medikiosk-web.log
   Ctrl-C to stop both.
  ────────────────────────────────────────────────────────────────

BANNER

wait
