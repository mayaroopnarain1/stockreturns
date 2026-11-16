#!/usr/bin/env bash
# One-command launcher for the StockLens web app (macOS / Linux).
#
#   bash scripts/run_local.sh            live data (Yahoo Finance + SEC EDGAR)
#   bash scripts/run_local.sh --fake     built-in demo data, no internet or yfinance needed
#   bash scripts/run_local.sh --port=9000
#
# It finds a suitable Python, makes a private .venv inside the project, installs
# what the API needs, and starts the server on all network interfaces so an
# iPhone on the same Wi-Fi can open it.
set -eo pipefail
cd "$(dirname "$0")/.."

FAKE=0
PORT=8000
for arg in "$@"; do
  case "$arg" in
    --fake) FAKE=1 ;;
    --port=*) PORT="${arg#--port=}" ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)"; exit 2 ;;
  esac
done

py_ok() { "$1" -c "import sys; sys.exit(0 if sys.version_info >= ($2, $3) else 1)" >/dev/null 2>&1; }

# Prefer Python 3.10+ (needed for live data); accept 3.9 (macOS default) with a warning.
PY="${STOCKLENS_PYTHON:-}"      # optional override: STOCKLENS_PYTHON=/path/to/python bash scripts/run_local.sh
for cand in python3.13 python3.12 python3.11 python3.10; do
  [ -n "$PY" ] && break
  if command -v "$cand" >/dev/null 2>&1 && py_ok "$cand" 3 10; then PY="$cand"; break; fi
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1 && py_ok python3 3 10; then PY="python3"; fi
if [ -n "$PY" ] && ! py_ok "$PY" 3 10; then
  echo "Note: $PY is older than Python 3.10; live-data packages may not install (demo data is the fallback)."
elif [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1 && py_ok python3 3 9; then
    PY="python3"
    echo "Note: only Python $(python3 -c 'import platform; print(platform.python_version())') found."
    echo "      Live-data packages may not install on it; I'll fall back to demo data if they don't."
    echo "      For live data install a newer Python:  brew install python@3.12   (or https://www.python.org/downloads/)"
    echo
  else
    echo "Python 3.9 or newer is required, but none was found."
    echo "Install one:  brew install python@3.12   (or download from https://www.python.org/downloads/)"
    exit 1
  fi
fi
echo "Using $($PY --version) ($(command -v "$PY"))"

# Private virtual environment inside the project (recreate if it was built with an unusable Python).
if [ -d .venv ] && ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then rm -rf .venv; fi
[ -d .venv ] || "$PY" -m venv .venv
VPY=".venv/bin/python"
"$VPY" -m pip install -q --upgrade pip >/dev/null 2>&1 || true

CORE='fastapi>=0.110,<1.0 uvicorn>=0.29,<1.0 pandas>=2.0,<3.0 numpy>=1.26,<3.0 requests>=2.31,<3.0'
echo "Installing packages (first run takes a minute)…"
if [ "$FAKE" -eq 1 ]; then
  # shellcheck disable=SC2086
  "$VPY" -m pip install -q $CORE
else
  if ! "$VPY" -m pip install -q -r requirements-api.txt; then
    echo
    echo "Could not install the live-data packages (yfinance). Starting with demo data instead."
    echo "To get live data, use Python 3.10+ and re-run this script."
    echo
    # shellcheck disable=SC2086
    "$VPY" -m pip install -q $CORE
    FAKE=1
  fi
fi

IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || true)"
echo
if [ "$FAKE" -eq 1 ]; then MODE="DEMO data - numbers are synthetic"; else MODE="live data"; fi
echo "StockLens is starting ($MODE)"
echo "  On this computer:  http://localhost:$PORT"
if [ -n "$IP" ]; then
  echo "  On your iPhone:    http://$IP:$PORT     (same Wi-Fi, type http:// yourself)"
  echo "  Connection check:  http://$IP:$PORT/api/health  should show {\"status\":\"ok\"...}"
fi
echo "Press Ctrl+C to stop."
echo

export STOCKLENS_BACKEND=api
[ "$FAKE" -eq 1 ] && export STOCKLENS_FAKE_DATA=1
exec "$VPY" -m uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
