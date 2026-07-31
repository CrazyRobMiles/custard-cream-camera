#!/bin/bash
# Launcher for desktop icons / application menu entries - finds its own
# location so it works regardless of where the repo is cloned or what the
# current working directory is when it's double-clicked.

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$DIR"

# API keys (GOOGLE_API_KEY, FLICKR_API_KEY, FLICKR_API_SECRET, ...) go in secrets.sh, not here -
# that file is gitignored, so real keys never end up committed. See docs/api-keys.md.
if [ -f "$DIR/secrets.sh" ]; then
    source "$DIR/secrets.sh"
fi

if [ -f "$DIR/venv/bin/activate" ]; then
    source "$DIR/venv/bin/activate"
fi

if [ -t 1 ]; then
    python3 custard_cream_camera_host.py
    status=$?
    if [ $status -ne 0 ]; then
        echo
        echo "custard_cream_camera_host.py exited with an error (status $status)."
        read -p "Press Enter to close this window..."
    fi
else
    # No terminal attached (e.g. launched from a desktop icon with
    # Terminal=false) - nothing to print to, so log instead.
    python3 custard_cream_camera_host.py >>"$DIR/custard_cream_camera_host.log" 2>&1
    status=$?
fi
