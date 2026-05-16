#!/bin/bash
# voice-to-form  —  run.command  v0.1.0
# Double-click launcher.  Activates the local venv and opens the GUI.

set -u

cd "$(dirname "$0")"
echo "voice-to-form run.command v0.1.0"
echo "working dir: $PWD"

if [ ! -d ".venv" ]; then
    echo
    echo "No .venv found.  Run setup.command first (double-click it)."
    echo
    read -p "Press Enter to close..."
    exit 1
fi

source .venv/bin/activate
python main.py
status=$?

echo
if [ $status -ne 0 ]; then
    echo "voice-to-form exited with status $status."
else
    echo "voice-to-form exited cleanly."
fi
read -p "Press Enter to close..."
