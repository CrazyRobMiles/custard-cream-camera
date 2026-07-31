
# Custard Cream Camera

![Image of the camera and a large rubber duck](/images/camera.JPG)

This repo holds two apps that share common code:

* **[camera/](camera/)** — the original Custard Cream Camera. Lets you take pictures, edit them and print them on a built-in printer. It can also publish pictures to Flickr, Bluesky, and a self-hosted Custard Cream Camera Server — pick which one from a menu on the Publish button.
* **[host/](host/)** — a camera-less companion app for a Sony camera's FTP photo-transfer feature. It receives JPEGs over FTP and gives them the same reviewing/printing/publishing/voice-editing treatment as the camera app's Play mode, targeting a more constrained Raspberry Pi (e.g. a Zero W 2) with no camera attached.

Reviewing, printing, publishing, and voice-editing photos is genuinely shared code, not two copies — see **[lib/](lib/)** for what's shared and why. Each app has its own `requirements.txt`, `settings.json`, venv, and docs tree, since they're meant to run on separate, independently-provisioned devices.

Inspired by the camera made by [Nikbuild](https://github.com/nickbild/banamera)

## Camera app

* [Setting Up the Python Virtual Environment](camera/docs/venv-setup.md) — create, activate, and (if needed) recreate the `venv` this app always runs inside.
* [Running the App](camera/docs/running-the-app.md) — start it from a terminal, or launch it from a desktop icon with no keyboard needed.
* [Display Backends](camera/docs/display-backends.md) — pick between an HDMI touchscreen or a native HDMI display, and configure it in `settings.json`.
* [Camera Orientation](camera/docs/camera-orientation.md) — fix an upside-down or mirrored viewfinder with `hflip`/`vflip`.
* [Exposure Compensation](camera/docs/exposure-compensation.md) — bias the auto-exposure with on-screen EV+/EV- buttons for backlit or overexposed scenes.
* [Capture Mode and Play Mode](camera/docs/capture-and-play-modes.md) — the live viewfinder vs. reviewing/printing/speaking/publishing existing photos.
* [Shutter Remotes](camera/docs/shutter-remote.md) — trigger photos and voice edits from a Bluetooth or wired USB-serial remote instead of the touchscreen; either or both can be enabled at once.
* [Audio Output (Shutter Sound)](camera/docs/audio-output.md) — a click sound plays when a photo is taken, configurable and safe to enable even with no audio hardware present.

## Host app (FTP receiver)

* [Setting Up the Python Virtual Environment](host/docs/venv-setup.md) — this app's own venv, separate from the camera app's.
* [Running the App](host/docs/running-the-app.md) — start it from a terminal, or launch it from a desktop icon with no keyboard needed.
* [Display Backends](host/docs/display-backends.md) — the same HDMI backends as the camera app.
* [Receiving Photos over FTP](host/docs/ftp-setup.md) — configuring the Sony camera's FTP-transfer feature to talk to this app, and how uploads get turned into previewable photos.
* [Reviewing Received Photos](host/docs/reviewing-photos.md) — stepping through, printing, speaking, and publishing whatever's arrived.

## Shared features (both apps)

* [Voice-Prompted AI Edits](camera/docs/voice-ai-edits.md) ([host version](host/docs/voice-ai-edits.md)) — record a spoken instruction and have Gemini edit the photo.
* [Printing](camera/docs/printing.md) ([host version](host/docs/printing.md)) — send photos to CUPS, test the pipeline without wasting paper, and add a watermark/date stamp.
* [Publishing to Flickr](camera/docs/publishing-flickr.md) ([host version](host/docs/publishing-flickr.md)) — one-time OAuth setup, then upload photos straight from the app.
* [Publishing to Bluesky](camera/docs/publishing-bsky.md) ([host version](host/docs/publishing-bsky.md)) — post photos with an app password, no OAuth needed.
* [Storing API Keys on the Device](camera/docs/api-keys.md) ([host version](host/docs/api-keys.md)) — get the Gemini/Flickr/Bluesky/server keys set automatically on every launch, without committing them to git.

## Hardware Setup Guides

* [Canon SELPHY CP400 + CUPS](camera/docs/printer-cups-setup.md) — get a CP400 dye-sublimation printer working with CUPS and Gutenprint on Raspberry Pi OS (identical setup for either app).
