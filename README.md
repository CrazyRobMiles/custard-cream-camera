
# Custard Cream Camera

![Image of the camera and a large rubber duck](/images/camera.JPG)

The Custard Cream Camera lets you take pictures, edit them and print them on a built in printer. It can also publish pictures to Flickr, Bluesky, and a self-hosted Custard Cream Camera Server — pick which one from a menu on the Publish button.

Inspired by the camera made by [Nikbuild](https://github.com/nickbild/banamera)

## Getting Started

* [Setting Up the Python Virtual Environment](docs/venv-setup.md) — create, activate, and (if needed) recreate the `venv` this project always runs inside.
* [Running the App](docs/running-the-app.md) — start it from a terminal, or launch it from a desktop icon with no keyboard needed.
* [Display Backends](docs/display-backends.md) — pick between the SPI LCD touchscreen or a native HDMI display, and configure it in `settings.json`.

## Using the Camera

* [Camera Orientation](docs/camera-orientation.md) — fix an upside-down or mirrored viewfinder with `hflip`/`vflip`.
* [Exposure Compensation](docs/exposure-compensation.md) — bias the auto-exposure with on-screen EV+/EV- buttons for backlit or overexposed scenes.
* [Capture Mode and Play Mode](docs/capture-and-play-modes.md) — the live viewfinder vs. reviewing/printing/speaking/publishing existing photos.
* [Voice-Prompted AI Edits](docs/voice-ai-edits.md) — record a spoken instruction and have Gemini edit the photo.
* [Shutter Remotes](docs/shutter-remote.md) — trigger photos and voice edits from a Bluetooth or wired USB-serial remote instead of the touchscreen; either or both can be enabled at once.
* [Audio Output (Shutter Sound)](docs/audio-output.md) — a click sound plays when a photo is taken, configurable and safe to enable even with no audio hardware present.

## Printing & Publishing

* [Printing](docs/printing.md) — send photos to CUPS, test the pipeline without wasting paper, and add a watermark/date stamp.
* [Publishing to Flickr](docs/publishing-flickr.md) — one-time OAuth setup, then upload photos straight from the app.
* [Publishing to Bluesky](docs/publishing-bsky.md) — post photos with an app password, no OAuth needed.
* [Storing API Keys on the Device](docs/api-keys.md) — get the Gemini/Flickr/Bluesky/server keys set automatically on every launch, without committing them to git.

## Hardware Setup Guides

* [Canon SELPHY CP400 + CUPS](docs/printer-cups-setup.md) — get a CP400 dye-sublimation printer working with CUPS and Gutenprint on Raspberry Pi OS.
