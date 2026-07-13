# Printing

The **Print** button (in [Play mode](capture-and-play-modes.md)) sends the currently displayed photo to CUPS (`lp <file>`) — see the [Canon SELPHY CP400 setup](printer-cups-setup.md) for getting a printer configured. `lp` only queues the job; if the printer is offline, out of paper, etc., that failure shows up in CUPS (`lpstat`, its web UI, or `/var/log/cups/error_log`) rather than in `magic_camera.py`.

By default `lp` is called with no `-d` flag, meaning it uses CUPS's configured default destination — if you get `lp: Error - No default destination`, either set one with `sudo lpadmin -d <printer-name>` (see `lpstat -p -d` for the list of configured printers and current default), or set `"printer": "<printer-name>"` under `"printing"` in [settings.json](../settings.json) to have the app always target that printer explicitly, independent of the system default.

## Print Testing

Set `"test_mode": true` under `"printing"` in [settings.json](../settings.json) to try out the print pipeline — watermark and date stamp included — without spending paper/ink: pressing **Print** saves the exact image that would have been sent to `lp` into `"test_folder"` (default `print_tests/`, gitignored) instead of actually printing it. The console prints exactly where it was saved. Set back to `false` (the default) to resume printing for real.

## Watermark and Date Stamp

Prints can have a watermark logo and/or a date/time stamp composited on automatically — implemented in [print_overlays.py](../print_overlays.py). Both are applied only to the copy sent to the printer (via a temporary file); the original saved photo in `captures/` is never modified.

**Watermark** (`"watermark"` in [settings.json](../settings.json)):

```json
"watermark": {
    "enabled": true,
    "file": "assets/images/watermark.png",
    "horizontal_align": "right",
    "vertical_align": "bottom",
    "width_fraction": 0.2,
    "margin_fraction": 0.02
}
```

* `"file"` — path to a PNG, relative to the repo root. Transparent areas show the photo through, so the source PNG needs an alpha channel (both files under [assets/images/](../assets/images/) already have one).
* `"horizontal_align"`/`"vertical_align"` — which corner: `"left"`/`"right"` and `"top"`/`"bottom"`.
* `"width_fraction"` — how wide the watermark should be, as a fraction of the photo's width (aspect ratio is preserved, so this also determines its height).
* `"margin_fraction"` — gap from the edges, as a fraction of the photo's width/height.

**Date stamp** (`"datestamp"` in settings.json):

```json
"datestamp": {
    "enabled": true,
    "format": "%Y-%m-%d %H:%M",
    "horizontal_align": "left",
    "vertical_align": "bottom",
    "font_fraction": 0.035,
    "margin_fraction": 0.02,
    "text_colour": [255, 255, 255, 255],
    "background_colour": [0, 0, 0, 140]
}
```

* `"format"` — a [`strftime`](https://docs.python.org/3/library/time.html#time.strftime) format string. The stamp reflects when the photo was actually taken (the file's modification time), not when it's printed.
* `"font_fraction"` — text size as a fraction of the photo's height.
* `"text_colour"`/`"background_colour"` — `[R, G, B, A]`; the background box (drawn behind the text for legibility over busy photos) defaults to semi-transparent black.

Both default to the bottom corners (watermark bottom-right, date stamp bottom-left) so they don't overlap — adjust either independently if you'd rather they sit elsewhere. If a watermark/date stamp fails to apply for any reason (bad path, corrupt font, etc.), that step is skipped with a printed error rather than blocking the print entirely.
