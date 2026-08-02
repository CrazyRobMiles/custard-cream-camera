import os
from pathlib import Path

from .base import BaseDisplay
from .widgets import Button


def _ensure_display_env():
    """Best-effort fallback for DISPLAY/XDG_RUNTIME_DIR when the process never inherited the
    desktop session's environment - e.g. launched from an SSH/remote-terminal shell rather than
    a terminal opened on the desktop itself. Activating a Python venv doesn't set these (it only
    touches PATH), so this can bite regardless of venv use, but shows up together with it since
    that's usually when people are running things from a fresh, non-desktop shell.

    Only fills in a value if it's missing, and only when there's real evidence of what it should
    be (an actual X11 socket, an actual runtime dir) - never invents one if no display truly
    exists, since then the original, correct error should still surface.
    """
    if not os.environ.get("DISPLAY"):
        x11_dir = Path("/tmp/.X11-unix")
        if x11_dir.is_dir():
            sockets = sorted(p.name for p in x11_dir.iterdir() if p.name.startswith("X"))
            if sockets:
                display_num = sockets[0][1:]  # "X0" -> "0"
                os.environ["DISPLAY"] = f":{display_num}"
                print(f"DISPLAY was not set - defaulting to :{display_num} (found {x11_dir / sockets[0]})")

    if not os.environ.get("XDG_RUNTIME_DIR"):
        runtime_dir = Path(f"/run/user/{os.getuid()}")
        if runtime_dir.is_dir():
            os.environ["XDG_RUNTIME_DIR"] = str(runtime_dir)
            print(f"XDG_RUNTIME_DIR was not set - defaulting to {runtime_dir}")


def create_display(settings=None):
    """Instantiate the display backend selected by settings["display"]["type"]."""

    settings = settings or {}
    display_settings = settings.get("display", {})
    display_type = display_settings.get("type", "hdmi-desktop")
    # Logical canvas size everything is drawn/laid out against - independent of the physical
    # window/output size, and configurable so a bigger canvas (more room for on-screen
    # text/keyboards) can be tried without committing to it if it costs too much frame rate.
    width = display_settings.get("width", 480)
    height = display_settings.get("height", 320)

    if display_type == "hdmi-desktop":
        _ensure_display_env()
        from .hdmi_desktop_display import HDMIDesktopDisplay
        return HDMIDesktopDisplay(width=width, height=height, **display_settings.get("hdmi-desktop", {}))

    raise ValueError(f"Unknown display type: {display_type!r}")


__all__ = ["BaseDisplay", "Button", "create_display"]
