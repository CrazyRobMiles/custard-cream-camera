# Display Backends

`custard_cream_camera_host.py` renders through the same pluggable display layer in [lib/displays/](../../lib/displays/) as the [camera app](../../camera/) - identical code, identical settings shape. Two backends are provided, both for devices with a native HDMI display:

* `hdmi-desktop` — a plain window via Tkinter, using the mouse for touch input ([lib/displays/hdmi_desktop_display.py](../../lib/displays/hdmi_desktop_display.py)). No fullscreen mode-switching or video driver selection — it just opens an ordinary window through whatever windowing system the desktop is already using, the same as any other desktop app. This is the simplest option and the one to try first.
* `hdmi-pygame` — a dedicated fullscreen SDL/pygame surface, using the mouse for touch input ([lib/displays/hdmi_pygame_display.py](../../lib/displays/hdmi_pygame_display.py)). Bypasses the desktop's window manager for lower-overhead fullscreen updates, at the cost of needing a working SDL video driver for your setup — reach for this only if `hdmi-desktop`'s performance isn't enough. Worth checking on a Pi Zero W 2, where the lower overhead may matter more than on a full-size Pi.

Select the backend and tune its options in [settings.json](../settings.json):

```json
{
    "display": {
        "type": "hdmi-desktop",
        "width": 800,
        "height": 480
    }
}
```

`hdmi-desktop` needs Tkinter, which on Raspberry Pi OS / Debian is a system package, not a pip one:

```bash
sudo apt install python3-tk
```

## `width`/`height` — the logical canvas size

Every screen (menus, the current photo, the on-screen keyboard) is drawn against a logical canvas of `width` x `height`, then scaled up to fill whatever the real window/output size is — so this is independent of `hdmi-pygame`'s own `window_width`/`window_height` (the *physical* SDL surface size). Defaults to `480`x`320` if omitted.

A bigger canvas gives more room for on-screen text and controls (e.g. the AI-prompt keyboard, see [Voice-Prompted AI Edits](voice-ai-edits.md)) at the cost of more pixels to draw per frame - worth watching on a Pi Zero W 2, which has much less headroom than the hardware the camera app usually runs on. If a larger size causes worse frame rates, drop `width`/`height` back down (or remove them entirely to fall back to `480`x`320`) — no code change needed either way.

## `DISPLAY`/`XDG_RUNTIME_DIR` not set

Both HDMI backends need `DISPLAY` (and ideally `XDG_RUNTIME_DIR`) set to reach the desktop session — normally automatic when logged into the Pi's own desktop, but **not** when launched from a plain SSH shell or a remote-dev tool's integrated terminal, which don't inherit those variables. Activating the Python venv doesn't set them either.

`lib/displays/__init__.py` fills in a best-effort default for either one if it's missing — it looks for a real X11 socket under `/tmp/.X11-unix` and a real `/run/user/<uid>` directory, and only sets the variable if it finds one, printing what it defaulted to. If it still can't find one — e.g. no desktop session is running at all — the underlying error will still surface.

## Touch/clicks stop responding, but the cursor still moves

If the touchscreen (or mouse) can move the cursor around but clicks don't register anywhere, the likely cause is a modal dialog left open somewhere behind the app, silently eating every click because it's waiting for you to click its own OK/Cancel first - see [Camera app: Touch/clicks stop responding](../../camera/docs/display-backends.md#touchclicks-stop-responding-but-the-cursor-still-moves) for the known trigger (a stray Flickr-auth browser/keyring dialog); the same cause applies here since both apps can publish to Flickr.
