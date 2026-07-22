# Printing

The **Print** button (in [Play mode](capture-and-play-modes.md)) sends the currently displayed photo to CUPS via [pycups](https://github.com/OpenPrinting/pycups) — see the [Canon SELPHY CP400 setup](printer-cups-setup.md) for getting a printer configured. Submitting and watching the job runs on a background thread, the same way [publishing](../publishers/) and [AI edits](voice-ai-edits.md) do, so the viewfinder/buttons stay responsive while it works.

If no `"printer"` is set under `"printing"` in [settings.json](../settings.json), the app falls back to CUPS's configured default destination — if neither exists, printing fails with "No printer configured" (check `lpstat -p -d` for the list of configured printers and current default, and `sudo lpadmin -d <printer-name>` to set one).

## Detecting a Failed Print

Submitting a job only confirms CUPS queued it, not that it actually came out — a paper jam or empty tray fails later, asynchronously. So after submitting, the app polls the job's status (`job-state`/`job-state-reasons`) via the same CUPS connection until it reaches a final state, and shows the result on screen:

* **Printed!** — the job completed.
* A specific reason (e.g. from `job-printer-state-message`, or the first `job-state-reasons` entry) — the job was canceled or aborted, most often by the printer itself (paper out, a jam).
* **Print taking longer than expected** — the job hadn't reached a final state after `"job_timeout_seconds"` (default `120`) under `"printing"` in settings.json; raise this if your printer is normally just slower than that.

Since real prints can take a minute or more on the CP400, this polling happens on the same background thread as the submission - see `run_print()`/`wait_for_print_job()` in `custard_cream_camera.py`.

## Recovering From a Stuck Queue

A print that fails outright (e.g. an empty paper tray) can leave CUPS with a disabled, rejecting queue for that printer — every print after it then just piles up in the spool instead of erroring, so nothing comes out even once the printer's fixed. To avoid that, before every print the app clears and re-enables the queue for whichever printer is configured (`reset_printer_queue()`, equivalent to running `cancel -a`, `cupsenable`, and `cupsaccept` on it), using the same CUPS connection as the job submission that follows.

Because this goes through pycups rather than shelling out, it doesn't need `sudo` — CUPS authorizes it directly against the caller's `lpadmin` group membership, the same membership set up in [Canon SELPHY CP400 setup](printer-cups-setup.md#add-your-user-to-the-printer-administration-group). If that account isn't in the group, this step fails, but only logs the failure rather than blocking the print attempt that follows.

## Print Testing

Set `"test_mode": true` under `"printing"` in [settings.json](../settings.json) to try out the print pipeline — watermark and date stamp included — without spending paper/ink: pressing **Print** saves the exact image that would have been sent to the printer into `"test_folder"` (default `print_tests/`, gitignored) instead of actually printing it. The console prints exactly where it was saved. Set back to `false` (the default) to resume printing for real.

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
