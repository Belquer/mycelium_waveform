#!/bin/bash
# voice-to-form  —  setup.command  v0.1.0
# First-time setup.  Creates .venv and installs requirements.

set -u

cd "$(dirname "$0")"
echo "voice-to-form setup.command v0.1.0"
echo "working dir: $PWD"
echo

# Prefer python3.12, fall back to whatever python3 is on PATH.
PYTHON=""
for cand in python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYTHON="$cand"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Could not find python3 / python3.11 / python3.12."
    echo "Install with: brew install python@3.12"
    read -p "Press Enter to close..."
    exit 1
fi

echo "Using $PYTHON  ($($PYTHON --version))"
echo

if [ ! -d ".venv" ]; then
    echo "Creating .venv…"
    "$PYTHON" -m venv .venv
fi

source .venv/bin/activate

echo "Upgrading pip…"
python -m pip install --upgrade pip

echo "Installing requirements (this can take 2–5 minutes on first run)…"
pip install -r requirements.txt
status=$?

echo
if [ $status -eq 0 ]; then
    echo "Setup OK.  Double-click run.command to launch the app."
else
    echo "Setup failed with status $status."
    echo
    echo "Common causes:"
    echo "  - Python 3.13/3.14: some science wheels (open3d, librosa) lag releases."
    echo "    Try python3.12 (brew install python@3.12) and re-run setup.command."
    echo "  - open3d on Apple Silicon: comment it out in requirements.txt; the"
    echo "    app falls back to trimesh-based decimation automatically."
fi
read -p "Press Enter to close..."
