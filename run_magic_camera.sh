#!/bin/bash
# Launcher for desktop icons / application menu entries - finds its own
# location so it works regardless of where the repo is cloned or what the
# current working directory is when it's double-clicked.

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$DIR"

if [ -f "$DIR/venv/bin/activate" ]; then
    source "$DIR/venv/bin/activate"
fi

if [ -t 1 ]; then
    python3 magic_camera.py
    status=$?
    if [ $status -ne 0 ]; then
        echo
        echo "magic_camera.py exited with an error (status $status)."
        read -p "Press Enter to close this window..."
    fi
else
    # No terminal attached (e.g. launched from a desktop icon with
    # Terminal=false) - nothing to print to, so log instead.
    python3 magic_camera.py >>"$DIR/magic_camera.log" 2>&1
    status=$?
fi
