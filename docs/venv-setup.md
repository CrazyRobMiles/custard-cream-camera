# Setting Up the Python Virtual Environment on Raspberry Pi OS

This app always runs inside a Python virtual environment — everything below happens in a `venv`,
nothing is installed into the system Python. What you install depends on which `"mode"` (see
[Home Screen: Camera Mode vs FTP Mode](home-screen-modes.md)) this device will run in — a
camera-mode device needs the Pi's camera stack, an FTP-mode device doesn't need anything camera
-related at all.

If you run this app on more than one device (one in camera mode, one in FTP mode), each device gets
its own independent venv at its own clone of this repo — there's no environment shared between them.

## Why `picamera2` needs special handling (camera mode only)

Almost every dependency (`pillow`, `numpy`) is a normal PyPI package and installs fine
into any plain venv via `requirements.txt` — no apt packages needed for those.

`picamera2` is the one exception, and it's only needed in camera mode. It's built on top of
`libcamera`, which talks directly to the Pi's camera ISP and tuning files, and is not published as a
portable pip wheel — it has to be the OS build from `apt` so it matches your kernel and camera
stack. A plain (isolated) venv can't see that OS-installed package, so a camera-mode device creates
its venv with `--system-site-packages`: this lets the venv see the apt-installed
`picamera2`/`libcamera`, while every other package still installs normally and independently via
`pip`. An FTP-mode device skips all of this and uses a plain, fully-isolated venv instead.

`pycups` (used for [printing](printing.md)) is a normal PyPI package too, but unlike the others it's
a C extension that links against CUPS's own headers at install time, so `libcups2-dev` needs to
already be on the system before `pip install -r requirements.txt` gets to it — needed either way.

## Installing System Packages

**Camera mode** — install `picamera2` and its `libcamera` dependency, plus the CUPS headers
`pycups` needs to build (Raspberry Pi OS / Debian-like):

```bash
sudo apt update
sudo apt install -y \
	python3-picamera2 \
	python3-libcamera \
	python3-venv \
	libcups2-dev
```

**FTP mode** — no camera stack needed:

```bash
sudo apt update
sudo apt install -y python3-venv libcups2-dev
```

Either mode, if you use the `hdmi-desktop` display backend (the default, see
[Display Backends](display-backends.md)), you also need Tkinter, a system package rather than a pip
one:

```bash
sudo apt install python3-tk
```

## Creating the Virtual Environment

**Camera mode** — needs `--system-site-packages` (see above):

```bash
python3 -m venv --system-site-packages venv
```

**FTP mode** — a plain, fully-isolated venv is enough:

```bash
python3 -m venv venv
```

## Activating the Virtual Environment

```bash
source venv/bin/activate
```

The command prompt should change to show that the virtual environment is active:

```text
(venv) rob@raspberrypi:~/custard-cream-camera $
```

## Installing Python Dependencies

Install the common packages, needed in either mode:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Camera mode only** — also install `picamera2` itself, kept in a separate
[requirements-camera.txt](../requirements-camera.txt) rather than the common `requirements.txt`,
since it isn't safely installable on an FTP-only device with no `libcamera` OS package present:

```bash
python -m pip install -r requirements-camera.txt
```

**Only if `"ai_edit.input_method"` is `"voice"` and `"custard_cream.transcribe_provider"` is
`"vosk"`** (see [Voice-Prompted AI Edits](voice-ai-edits.md)) — install `vosk` itself, kept in its
own [requirements-vosk.txt](../requirements-vosk.txt) rather than the common `requirements.txt`,
since it's a real cost (see below) not worth paying on a device that never uses it — e.g. a
low-spec keyboard/preset-only image receiver:

```bash
python -m pip install -r requirements-vosk.txt
```

## Installing Vosk (Local Speech Recognition)

`vosk` (used for offline transcription in [Voice-Prompted AI Edits](voice-ai-edits.md)) is a normal PyPI package, installed via `requirements-vosk.txt` above — no apt package needed, either mode. Prebuilt wheels are published for 64-bit Raspberry Pi OS (aarch64); older 32-bit (armv7) installs may need to build from source — a Raspberry Pi Zero W 2 (a common choice for FTP mode) is aarch64-capable but ships 32-bit Raspberry Pi OS by default, so check which image you're running before assuming a prebuilt wheel is available.

Unlike the Python package, the **speech model itself is not installed by pip** — it's a separate download you place on disk yourself:

```bash
cd ~/custard-cream-camera
mkdir -p models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip -d models
rm vosk-model-small-en-us-0.15.zip
```

This should leave a `models/vosk-model-small-en-us-0.15/` folder, matching the default `"custard_cream.vosk.model_path"` in `settings.json` — adjust that setting if you download a different model or unzip it elsewhere. Larger/more accurate models are listed at [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models); the vosk-small model (~40MB) is a deliberately lightweight default, useful if this device is a lower-powered Pi.

This model is loaded once at app startup (not lazily on first use), so a missing or misconfigured `model_path` will fail the whole app on launch while `"custard_cream.transcribe_provider"` is set to `"vosk"` (the default) — verify it loads before relying on it:

```bash
python -c "import vosk; vosk.Model('models/vosk-model-small-en-us-0.15'); print('Vosk model OK')"
```

## Verifying Camera Support (camera mode only)

To check that the virtual environment can access the Raspberry Pi camera libraries:

```bash
python -c "from picamera2 import Picamera2; print('Picamera2 OK')"
```

and:

```bash
python -c "import libcamera; print('libcamera OK')"
```

## Deactivating the Virtual Environment

When you have finished working:

```bash
deactivate
```

This returns you to the system Python environment.

## Recreating the Environment

If the environment becomes corrupted or you want to start again:

```bash
deactivate
rm -rf venv

python3 -m venv --system-site-packages venv   # or plain "venv" for an FTP-mode device
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-camera.txt   # camera mode only
python -m pip install -r requirements-vosk.txt      # only if using voice input with the vosk provider
```

## Notes

* Do not commit the `venv` folder to Git.
* Add `venv/` to `.gitignore`.
* `requirements.txt`/`requirements-camera.txt`/`requirements-vosk.txt` should contain only packages installed via `pip`.
* Raspberry Pi OS packages such as Picamera2 should be installed using `apt`, not added to any requirements file.
