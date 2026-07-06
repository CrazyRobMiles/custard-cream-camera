#!/bin/bash
# Launcher for desktop icons / application menu entries - finds its own
# location so it works regardless of where the repo is cloned or what the
# current working directory is when it's double-clicked.

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$DIR"

if [ -f "$DIR/venv/bin/activate" ]; then
    source "$DIR/venv/bin/activate"
fi

python3 magic_camera.py
status=$?

if [ $status -ne 0 ]; then
    echo
    echo "magic_camera.py exited with an error (status $status)."
    read -p "Press Enter to close this window..."
fi
