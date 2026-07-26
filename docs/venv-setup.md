# Setting Up the Python Virtual Environment on Raspberry Pi OS

This project always runs inside a Python virtual environment — everything below happens in a `venv`, nothing is installed into the system Python. The only wrinkle on a Raspberry Pi is `picamera2`.

## Why Use `--system-site-packages`?

Almost every dependency (`pillow`, `numpy`, `pygame`) is a normal PyPI package and installs fine into any plain venv via `requirements.txt` — no apt packages needed for those.

`picamera2` is the one exception. It's built on top of `libcamera`, which talks directly to the Pi's camera ISP and tuning files, and is not published as a portable pip wheel — it has to be the OS build from `apt` so it matches your kernel and camera stack. A plain (isolated) venv can't see that OS-installed package, so we create the venv with `--system-site-packages`: this lets the venv see the apt-installed `picamera2`/`libcamera`, while every other package still installs normally and independently via `pip`.

`pycups` (used for [printing](printing.md)) is a normal PyPI package too, but unlike the others it's a C extension that links against CUPS's own headers at install time, so `libcups2-dev` needs to already be on the system before `pip install -r requirements.txt` gets to it.

## Installing System Packages

Install `picamera2` and its `libcamera` dependency, plus the CUPS headers `pycups` needs to build (Raspberry Pi OS / Debian-like):

```bash
sudo apt update
sudo apt install -y \
	python3-picamera2 \
	python3-libcamera \
	python3-venv \
	libcups2-dev
```

## Creating the Virtual Environment

From the root of the repository:

```bash
python3 -m venv --system-site-packages venv
```

This creates a virtual environment in the `venv` folder.

## Activating the Virtual Environment

```bash
source venv/bin/activate
```

The command prompt should change to show that the virtual environment is active:

```text
(venv) rob@raspberrypi:~/my-project $
```

## Installing Python Dependencies

Install the packages listed in `requirements.txt`:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

These packages are installed into the virtual environment and do not affect the system Python installation.

## Installing Vosk (Local Speech Recognition)

`vosk` (used for offline transcription in [Voice-Prompted AI Edits](voice-ai-edits.md)) is a normal PyPI package, already listed in `requirements.txt`, so `pip install -r requirements.txt` above installs it like everything else — no apt package needed. Prebuilt wheels are published for 64-bit Raspberry Pi OS (aarch64); older 32-bit (armv7) installs may need to build from source.

Unlike the Python package, the **speech model itself is not installed by pip** — it's a separate download you place on disk yourself:

```bash
cd ~/my-project   # repository root
mkdir -p models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip -d models
rm vosk-model-small-en-us-0.15.zip
```

This should leave a `models/vosk-model-small-en-us-0.15/` folder, matching the default `"custard_cream.vosk.model_path"` in `settings.json` — adjust that setting if you download a different model or unzip it elsewhere. Larger/more accurate models are listed at [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models).

This model is loaded once at app startup (not lazily on first use), so a missing or misconfigured `model_path` will fail the whole app on launch while `"custard_cream.transcribe_provider"` is set to `"vosk"` (the default) — verify it loads before relying on it:

```bash
python -c "import vosk; vosk.Model('models/vosk-model-small-en-us-0.15'); print('Vosk model OK')"
```

## Verifying Camera Support

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

python3 -m venv --system-site-packages venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

## Notes

* Do not commit the `venv` folder to Git.
* Add `venv/` to `.gitignore`.
* The `requirements.txt` file should contain only packages installed via `pip`.
* Raspberry Pi OS packages such as Picamera2 should be installed using `apt`, not added to `requirements.txt`.
