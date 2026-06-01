#!/usr/bin/env bash
#
# Atomizer — one-shot setup for Apple Silicon (M1/M2/M3/M4), macOS 13+.
#
# Creates a Python 3.12 virtualenv, installs ffmpeg (Homebrew) and all Python
# dependencies, and prepares the .env file.
#
# Usage:
#   ./setup.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Atomizer setup"
echo "    dir: $SCRIPT_DIR"

# --- 1. Architecture check --------------------------------------------------
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "!! Warning: this machine is not Apple Silicon (arm64). MLX requires Apple Silicon."
fi

# --- 2. ffmpeg (via Homebrew) ----------------------------------------------
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "==> Installing ffmpeg via Homebrew..."
    brew install ffmpeg
  else
    echo "!! ffmpeg not found and Homebrew is not installed."
    echo "   Install Homebrew from https://brew.sh then run: brew install ffmpeg"
    exit 1
  fi
else
  echo "==> ffmpeg found: $(command -v ffmpeg)"
fi

# --- 3. Python 3.12 ---------------------------------------------------------
PY=""
for c in python3.12 python3.11 python3.10; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [[ -z "$PY" ]]; then
  echo "!! No Python 3.10–3.12 found. Install one (e.g. 'brew install python@3.12')."
  exit 1
fi
echo "==> Using $($PY --version) ($PY)"

# --- 4. virtualenv ----------------------------------------------------------
if [[ ! -d .venv ]]; then
  echo "==> Creating virtualenv .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip

# --- 5. Python deps ---------------------------------------------------------
echo "==> Installing Python dependencies (this can take a while)..."
pip install -r requirements.txt

# --- 6. .env ----------------------------------------------------------------
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Created .env from .env.example (edit it to add an optional BPM/key API key)."
fi

# --- 7. Pre-download recommended models ------------------------------------
# Pass --no-models to skip (models then download lazily on first use, with UI
# progress). Default: fetch everything now so the app is ready offline.
if [[ "${1:-}" != "--no-models" ]]; then
  echo "==> Pre-downloading recommended models (several GB; first time only)…"
  echo "    (skip with: ./setup.sh --no-models)"
  python -m atomizer.bootstrap || echo "!! Model pre-download had issues; they will retry on first use."
else
  echo "==> Skipping model pre-download (--no-models). They'll download on first use."
fi

echo
echo "==> Done. Run the app with:"
echo "    source .venv/bin/activate && python -m atomizer.main"
