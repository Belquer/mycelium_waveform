#!/bin/bash
# voice-to-form  —  voice-to-form.command  v0.2.0
# Single double-click launcher.  Creates the venv + installs deps on
# first run, then runs the GUI.  Subsequent launches skip setup.

set -u

cd "$(dirname "$0")"
echo "voice-to-form launcher v0.2.0"
echo "working dir: $PWD"
echo

# ------------------------------------------------------------------
# First-run setup: create .venv + install requirements
# ------------------------------------------------------------------
if [ ! -d ".venv" ] || [ ! -f ".venv/.setup_complete" ]; then
    echo "First run — setting up the Python environment."
    echo "(This step happens once, takes 2–5 minutes.)"
    echo

    PYTHON=""
    for cand in python3.12 python3.11 python3.13 python3; do
        if command -v "$cand" >/dev/null 2>&1; then
            PYTHON="$cand"
            break
        fi
    done

    if [ -z "$PYTHON" ]; then
        echo "Could not find python3 / python3.11 / python3.12."
        echo "Install with:  brew install python@3.12"
        echo
        read -p "Press Enter to close..."
        exit 1
    fi

    echo "Using $PYTHON  ($($PYTHON --version))"
    echo

    if [ ! -d ".venv" ]; then
        echo "Creating .venv…"
        "$PYTHON" -m venv .venv
    fi

    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install --upgrade pip
    echo
    echo "Installing requirements…"
    if ! pip install -r requirements.txt; then
        echo
        echo "Install failed.  Common causes:"
        echo "  - Python 3.13/3.14: some science wheels lag releases."
        echo "    Try:  brew install python@3.12  and delete .venv, run again."
        echo "  - open3d on Apple Silicon: comment out in requirements.txt;"
        echo "    decimation falls back to trimesh automatically."
        echo
        read -p "Press Enter to close..."
        exit 1
    fi

    touch .venv/.setup_complete
    echo
    echo "Setup OK.  Launching app…"
    echo "----------------------------------------------------------"
else
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

# ------------------------------------------------------------------
# Run the GUI
# ------------------------------------------------------------------
python main.py
status=$?

echo
if [ $status -ne 0 ]; then
    echo "voice-to-form exited with status $status."
else
    echo "voice-to-form exited cleanly."
fi
read -p "Press Enter to close..."
