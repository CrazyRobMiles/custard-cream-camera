# Setting Up the Python Virtual Environment on Raspberry Pi OS

This app always runs inside a Python virtual environment — everything below happens in a `venv`, nothing is installed into the system Python. It has its own venv, separate from the [camera app](../../camera/)'s — the two apps share code via [lib/](../../lib/) but not a Python environment, since they're meant to run on different, independently-provisioned devices.

Unlike the camera app, nothing here needs `--system-site-packages`: there's no `picamera2`/`libcamera` OS package to see through into the venv, since this app has no camera at all. A plain, fully-isolated venv is enough.

`pycups` (used for [printing](printing.md)) is a normal PyPI package, but it's a C extension that links against CUPS's own headers at install time, so `libcups2-dev` needs to already be on the system before `pip install -r requirements.txt` gets to it.

## Installing System Packages

```bash
sudo apt update
sudo apt install -y python3-venv libcups2-dev
```

If you use the `hdmi-desktop` display backend (the default, see [Display Backends](display-backends.md)), you also need Tkinter, a system package rather than a pip one:

```bash
sudo apt install python3-tk
```

## Creating the Virtual Environment

From this app's own folder (`host/` - the [camera app](../../camera/) has its own separate venv, see `camera/docs/venv-setup.md`):

```bash
python3 -m venv venv
```

## Activating the Virtual Environment

```bash
source venv/bin/activate
```

## Installing Python Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Installing Vosk (Local Speech Recognition)

`vosk` (used for offline transcription in [Voice-Prompted AI Edits](voice-ai-edits.md)) is already in `requirements.txt`. Prebuilt wheels are published for 64-bit Raspberry Pi OS (aarch64); older 32-bit (armv7) installs may need to build from source - a Raspberry Pi Zero W 2 (the target for this app) is aarch64-capable but ships 32-bit Raspberry Pi OS by default, so check which image you're running before assuming a prebuilt wheel is available.

The **speech model itself is not installed by pip** - it's a separate download you place on disk yourself:

```bash
cd ~/custard-cream-camera/host
mkdir -p models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip -d models
rm vosk-model-small-en-us-0.15.zip
```

This should leave a `models/vosk-model-small-en-us-0.15/` folder, matching the default `"custard_cream.vosk.model_path"` in `settings.json`. This model is loaded once at app startup, so a missing or misconfigured `model_path` will fail the whole app on launch while `"custard_cream.transcribe_provider"` is set to `"vosk"` (the default) - verify it loads before relying on it:

```bash
python -c "import vosk; vosk.Model('models/vosk-model-small-en-us-0.15'); print('Vosk model OK')"
```

The vosk-small model (~40MB) is deliberately the lightweight option, given this app targets a Pi Zero W 2 rather than a more powerful Pi.

## Deactivating the Virtual Environment

```bash
deactivate
```

## Recreating the Environment

```bash
deactivate
rm -rf venv

python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

## Notes

* Do not commit the `venv` folder to Git.
* `requirements.txt` should contain only packages installed via `pip`.
