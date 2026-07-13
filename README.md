
# Custard Cream Camera

A homage to the one made by [Nikbuild](https://github.com/nickbild/banamera)

This repository provides a small Python app that captures video from the
Raspberry Pi HQ Camera using `picamera2` and displays it on an LCD panel. You can then use AI prompts to edit the picture.

## Getting Started

* [Setting Up the Python Virtual Environment](docs/venv-setup.md) — create, activate, and (if needed) recreate the `venv` this project always runs inside.
* [Running the App](docs/running-the-app.md) — start it from a terminal, or launch it from a desktop icon with no keyboard needed.
* [Display Backends](docs/display-backends.md) — pick between the SPI LCD touchscreen or a native HDMI display, and configure it in `settings.json`.

## Using the Camera

* [Camera Orientation](docs/camera-orientation.md) — fix an upside-down or mirrored viewfinder with `hflip`/`vflip`.
* [Exposure Compensation](docs/exposure-compensation.md) — bias the auto-exposure with on-screen EV+/EV- buttons for backlit or overexposed scenes.
* [Image Browser](docs/image-browser.md) — how Speak/Print/Publish let you pick which photo to act on.
* [Voice-Prompted AI Edits](docs/voice-ai-edits.md) — record a spoken instruction and have Gemini edit the photo.
* [Bluetooth Shutter Remote](docs/shutter-remote.md) — trigger photos and voice edits from a physical remote instead of the touchscreen.

## Printing & Publishing

* [Printing](docs/printing.md) — send photos to CUPS, test the pipeline without wasting paper, and add a watermark/date stamp.
* [Publishing to Flickr](docs/publishing-flickr.md) — one-time OAuth setup, then upload photos straight from the app.

## Hardware Setup Guides

* [Canon SELPHY CP400 + CUPS](docs/printer-cups-setup.md) — get a CP400 dye-sublimation printer working with CUPS and Gutenprint on Raspberry Pi OS.
