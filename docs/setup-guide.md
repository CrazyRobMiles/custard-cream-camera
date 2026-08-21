# Setting Up From Scratch

A step-by-step walkthrough for taking a fresh Raspberry Pi OS install to a running Custard Cream
Camera. Follow the steps in order — later steps assume earlier ones are done. Each step links to a
dedicated doc for full detail/troubleshooting; this page is the map that ties them together and
tells you what order to actually do them in.

If you're setting up more than one physical device (e.g. one camera, one FTP receiver), repeat this
whole guide independently for each one — every device gets its own clone, venv, `secrets.sh`, and
`settings.json`; nothing is shared between them.

## 1. Decide the mode

`settings.json`'s `"mode"` key picks the home screen this device shows, and affects several of the
steps below:

* **`"camera"`** — a live viewfinder with Capture/Play modes; this device has a Pi camera attached.
* **`"ftp"`** — no camera; this device receives JPEGs over FTP from a real camera (e.g. a Sony
  body's FTP-transfer feature) and is always in Play mode.

See [Home Screen: Camera Mode vs FTP Mode](home-screen-modes.md) for exactly what differs. Steps
below are marked **[camera mode]** or **[FTP mode]** where they only apply to one.

## 2. Get the code onto the device

```bash
git clone https://github.com/CrazyRobMiles/custard-cream-camera.git
cd custard-cream-camera
```

## 3. Install system packages

These come from `apt`, not `pip` — see [Setting Up the Python Virtual Environment](venv-setup.md)
for why `picamera2` in particular has to be installed this way.

**[camera mode]**
```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-libcamera python3-venv libcups2-dev python3-tk
```

**[FTP mode]**
```bash
sudo apt update
sudo apt install -y python3-venv libcups2-dev python3-tk
```

(`python3-tk` is only needed if you use the `hdmi-desktop` display backend — the default and, at
the moment, the only one — see [Display Backends](display-backends.md).)

## 4. Create and activate the virtual environment

**[camera mode]** needs `--system-site-packages` so the venv can see the apt-installed
`picamera2`/`libcamera`:
```bash
python3 -m venv --system-site-packages venv
```

**[FTP mode]** a plain, fully-isolated venv is enough:
```bash
python3 -m venv venv
```

Then, either mode:
```bash
source venv/bin/activate
python -m pip install --upgrade pip
```

Full detail (recreating the environment, verifying camera support, etc.) is in
[Setting Up the Python Virtual Environment](venv-setup.md).

## 5. Install Python dependencies

Common packages, either mode:
```bash
python -m pip install -r requirements.txt
```

**[camera mode] only** — `picamera2` itself:
```bash
python -m pip install -r requirements-camera.txt
```

**Only if you'll use voice AI edits with the local Vosk transcriber** (step 10 below covers whether
you need this):
```bash
python -m pip install -r requirements-vosk.txt
```
— then download a Vosk model; see
[Installing Vosk](venv-setup.md#installing-vosk-local-speech-recognition) for the exact commands.

## 6. Create `settings.json`

```bash
cp settings.json.example settings.json
```

Set `"mode"` to `"camera"` or `"ftp"` per step 1. Everything below edits this same file — it's
listed in `.gitignore`, so it's device-local config: a `git pull` on this device never overwrites
it, and none of the values you set below get committed back to the repo.

## 7. Configure the display

Check `"display"` in `settings.json` matches your screen's actual resolution:
```json
"display": { "type": "hdmi-desktop", "width": 800, "height": 480 }
```
See [Display Backends](display-backends.md) for what `width`/`height` mean and how to fix a blank
window (`DISPLAY`/`XDG_RUNTIME_DIR` not set — common over SSH).

## 8. [camera mode] Fix the viewfinder orientation

If the live preview comes out upside-down or mirrored (common — the sensor is often mounted rotated
in the enclosure), set `"hflip"`/`"vflip"` under `"camera"` in `settings.json` before going further,
since every later camera-mode step assumes you're looking at a correctly-oriented preview. See
[Camera Orientation](camera-orientation.md).

## 9. [FTP mode] Configure the FTP receiver

Set the `"ftp"` block in `settings.json` (host/port/username/password), then configure the sending
camera's FTP-transfer feature to point at this device. Full walkthrough, including a way to test it
without a real camera: [Receiving Photos over FTP](ftp-setup.md).

## 10. Decide which optional features you need, and get API keys for them

Everything below this point is optional — skip whichever features you don't need. Each one needs an
API key stored as an environment variable (never in `settings.json`, since that's checked into
git). Set up however many of these you actually plan to use:

| Feature | Env vars needed | Where to get them |
|---|---|---|
| [Voice-Prompted AI Edits](voice-ai-edits.md) | `GOOGLE_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| [Publishing to Flickr](publishing-flickr.md) | `FLICKR_API_KEY`, `FLICKR_API_SECRET` | [flickr.com/services/apps/create](https://www.flickr.com/services/apps/create/) |
| [Publishing to Bluesky](publishing-bsky.md) | `BSKY_HANDLE`, `BSKY_APP_PASSWORD` | [bsky.app/settings/app-passwords](https://bsky.app/settings/app-passwords) |
| Publishing to a self-hosted Custard Cream Server | `CUSTARD_CREAM_SERVER_EMAIL`, `CUSTARD_CREAM_SERVER_PASSWORD` | your server account's login |

To make these available to the app automatically on every launch (including from a desktop icon,
where there's no terminal to `export` into), set them up in `secrets.sh` now, before enabling the
features that need them:
```bash
cp secrets.sh.example secrets.sh
chmod 600 secrets.sh
```
Edit `secrets.sh` and fill in whichever keys apply. Full detail (including a fallback option and
why `secrets.sh` and not `~/.bashrc`) in [Storing API Keys on the Device](api-keys.md).

Flickr needs one extra one-time step — a browser-based OAuth authorization — covered in
[Publishing to Flickr](publishing-flickr.md#one-time-setup); do this now while you're already in
the API-key mindset, since it also needs `FLICKR_API_KEY`/`FLICKR_API_SECRET` set first.

## 11. Turn on the AI-edit feature (optional)

Set `"ai_edit.enabled"`/`"ai_edit.input_method"` in `settings.json` — `"voice"` (hold-to-talk) or
`"keyboard"` (tap, pick a preset or type one). If using `"voice"` with the local Vosk provider,
confirm the model loads (step 5 covers installing it):
```bash
python -c "import vosk; vosk.Model('models/vosk-model-small-en-us-0.15'); print('Vosk model OK')"
```
Either input method also needs a working microphone — see
[Voice-Prompted AI Edits § Setup](voice-ai-edits.md#setup) for the `arecord` test command and full
detail on both input methods.

## 12. Turn on publishing destinations (optional)

For each destination you set up keys for in step 10, set its `"enabled"` and the rest of its block
under `"publish"` in `settings.json` — see [Publishing to Flickr](publishing-flickr.md#configuration)
and [Publishing to Bluesky](publishing-bsky.md#configuration) for the options each one takes.

## 13. Set up printing (optional)

Get a printer working with CUPS first — [Canon SELPHY CP400 + CUPS](printer-cups-setup.md) if
you're using that specific printer, otherwise get any printer showing up in `lpstat -p -d`. Then
set `"printing.printer"` in `settings.json` to its CUPS name (or leave it `null` to use whatever
CUPS' own default is). Turn on a watermark/date stamp on printed copies via the `"watermark"`/
`"datestamp"` blocks if wanted. Full detail: [Printing](printing.md).

## 14. [camera mode] Set up extras (optional)

* [Exposure Compensation](exposure-compensation.md) — the EV-/EV+ range/step, under `"exposure"`.
* [Shutter Remotes](shutter-remote.md) — Bluetooth, wired USB-serial, and/or GPIO button, any
  combination, under `"shutter_remote"`/`"serial_remote"`/`"gpio_remote"`.
* [Audio Output (Shutter Sound)](audio-output.md) — the click sound played on capture, under
  `"audio_output"`.

## 15. First run

```bash
python custard_cream_camera.py
```
See [Running the App](running-the-app.md) for what to expect on screen in each mode, and keyboard
shortcuts (`q` to quit, spacebar to shoot) available when launched from a terminal.

## 16. Set up launch-from-desktop-icon (optional, for a device with no keyboard)

Once step 15 works from a terminal, [run_custard_cream_camera.sh](../run_custard_cream_camera.sh)
and [custard-cream-camera.desktop](../custard-cream-camera.desktop) let the same thing launch by
double-clicking an icon instead. See [Running the App § From a Desktop Icon](running-the-app.md#from-a-desktop-icon)
for installing it and the file-manager quirks (executable bit, "untrusted" prompts) that trip this
up on a fresh clone.

## Done

At this point you have a working device. From here, the docs listed in the README's
[Reference](../README.md#reference) section cover each feature in more depth than this walkthrough
does — go there when you want to change how something already set up here behaves, or when
troubleshooting something specific.
