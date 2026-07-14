# Display Backends

`custard_cream_camera.py` renders through a pluggable display layer in [displays/](../displays/). Three backends are provided:

* `ili9486` — the SPI ILI9486 LCD + XPT2046 touch panel ([displays/ili9486_display.py](../displays/ili9486_display.py))
* `hdmi-desktop` — a plain window via Tkinter, using the mouse for touch input ([displays/hdmi_desktop_display.py](../displays/hdmi_desktop_display.py)). No fullscreen mode-switching or video driver selection — it just opens an ordinary window through whatever windowing system the desktop is already using, the same as any other desktop app. This is the simplest option and the one to try first on a device with a native HDMI display.
* `hdmi-pygame` — a dedicated fullscreen SDL/pygame surface, using the mouse for touch input ([displays/hdmi_pygame_display.py](../displays/hdmi_pygame_display.py)). Bypasses the desktop's window manager for lower-overhead fullscreen updates, at the cost of needing a working SDL video driver for your setup — reach for this only if `hdmi-desktop`'s performance isn't enough.

Select the backend and tune its options in [settings.json](../settings.json):

```json
{
    "display": {
        "type": "ili9486"
    }
}
```

Set `"type"` to `"hdmi-desktop"` or `"hdmi-pygame"` to run on a device with a native HDMI display instead. `hdmi-desktop` needs Tkinter, which on Raspberry Pi OS / Debian is a system package, not a pip one:

```bash
sudo apt install python3-tk
```

## `DISPLAY`/`XDG_RUNTIME_DIR` not set

Both HDMI backends need `DISPLAY` (and ideally `XDG_RUNTIME_DIR`) set to reach the desktop session — normally automatic when logged into the Pi's own desktop, but **not** when launched from a plain SSH shell or a remote-dev tool's integrated terminal (e.g. VS Code Remote-SSH), which don't inherit those variables. Activating the Python venv doesn't set them either (it only touches `PATH`), so this can bite regardless of venv use.

`displays/__init__.py` fills in a best-effort default for either one if it's missing — it looks for a real X11 socket under `/tmp/.X11-unix` and a real `/run/user/<uid>` directory, and only sets the variable if it finds one (it won't invent a display that doesn't actually exist), printing what it defaulted to. This should cover the common case of a single desktop session on `:0` without you needing to `export` anything by hand. If it still can't find one — e.g. no desktop session is running at all — the underlying error will still surface, since at that point there's genuinely nothing to connect to.
