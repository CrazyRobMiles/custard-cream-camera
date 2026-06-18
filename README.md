
# Nanobanana Camera

A homage to the one made by [Nikbuild](https://github.com/nickbild/banamera)

This repository provides a small Python app that captures video from the
Raspberry Pi HQ Camera using `picamera2` and displays it on an LCD panel. You can then use AI prompts to edit the picture using Nanobanana. 

# Setting Up the Python Virtual Environment on Raspberry Pi OS

This project uses a Python virtual environment to isolate its Python dependencies from the operating system. The virtual environment is configured to use Raspberry Pi OS system packages, which allows access to hardware-specific libraries such as Picamera2 and libcamera while keeping project-specific packages separate.

## Why Use `--system-site-packages`?

Some Raspberry Pi libraries are supplied by the operating system rather than PyPI. Examples include:

* Picamera2
* libcamera
* GPIO libraries
* Other hardware-specific packages

A standard virtual environment cannot see these packages. Creating the virtual environment with the `--system-site-packages` option allows the project to use them while still isolating any additional Python packages installed with `pip`.

## Installing System Packages

Install system packages (Raspberry Pi OS / Debian-like):

```bash
sudo apt update
sudo apt install -y \
	python3-picamera2 \
	python3-opencv \
	python3-numpy \
	ffmpeg \
	libsndfile1 \
	alsa-utils \
	pulseaudio
    python3-venv \
    python3-libcamera
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

## Verifying Camera Support

To check that the virtual environment can access the Raspberry Pi camera libraries:

```bash
python -c "from picamera2 import Picamera2; print('Picamera2 OK')"
```

and:

```bash
python -c "import libcamera; print('libcamera OK')"
```

# Using a Canon SELPHY CP400 with Raspberry Pi and CUPS

A good way to get cheap hard copy connect a Canon SELPHY CP400 dye-sublimation photo printer your a Raspberry Pi.

## Hardware Used

* Raspberry Pi (tested on Raspberry Pi 5)
* Canon SELPHY CP400
* Canon KP-36IP postcard media pack
* USB connection between printer and Pi

## Add Your User to the Printer Administration Group

Installations and printer management require membership of the `lpadmin` group.

```bash
sudo usermod -aG lpadmin $USER
```

Log out and back in after running this command.

Verify membership:

```bash
groups
```

You should see `lpadmin` in the list.

## Install CUPS

Install the CUPS printing system:

```bash
sudo apt update
sudo apt install cups
```

Enable and start CUPS:

```bash
sudo systemctl enable cups
sudo systemctl start cups
```

Check that it is running:

```bash
systemctl status cups
```

## Install Gutenprint

The Raspberry Pi package repository contains a Gutenprint package:

```bash
sudo apt install printer-driver-gutenprint
```

Unfortunately, the packaged version may contain a bug that prevents the CP400 from recognising postcard media correctly.

Typical error:

```text
Incorrect paper loaded (01 vs 11), aborting job!
```

If you encounter this error, build Gutenprint from source as described below.

## Building Gutenprint from Source

Install build dependencies:

```bash
sudo apt install \
    build-essential \
    libcups2-dev \
    libcupsimage2-dev \
    libusb-1.0-0-dev \
    libtiff-dev \
    libjpeg-dev \
    libpng-dev \
    gettext
```

Download and unpack Gutenprint:

```bash
wget https://downloads.sourceforge.net/project/gimp-print/gutenprint-5.3/5.3.3/gutenprint-5.3.3.tar.xz

tar xf gutenprint-5.3.3.tar.xz

cd gutenprint-5.3.3
```

Build and install:

```bash
./configure
make -j4
sudo make install
```

Restart CUPS:

```bash
sudo systemctl restart cups
```

## Discover the Printer

Connect the CP400 via USB and run:

```bash
lpinfo -v
```

Typical output:

```text
direct gutenprint53+usb://canon-cp400/NONE_UNKNOWN
```

Find the available driver:

```bash
lpinfo -m | grep -i cp400
```

Typical output:

```text
gutenprint.5.3://canon-cp400/expert Canon SELPHY CP400
```

## Create the Printer

Create the printer using the discovered URI and driver:

```bash
sudo lpadmin \
    -p SELPHY_CP400 \
    -E \
    -v "gutenprint53+usb://canon-cp400/NONE_UNKNOWN" \
    -m "gutenprint.5.3://canon-cp400/expert"
```

Enable the printer:

```bash
sudo cupsenable SELPHY_CP400
sudo cupsaccept SELPHY_CP400
```

Make it the default printer:

```bash
sudo lpadmin -d SELPHY_CP400
```

## Verify Page Size

Check available page sizes:

```bash
lpoptions -p SELPHY_CP400 -l | grep PageSize
```

Expected output:

```text
PageSize/Media Size: *Postcard w253h337 w155h244 w283h566
```

The asterisk indicates the current default.

The CP400 should normally use:

```text
Postcard
```

when printing KP-36IP media.

## Paper Size Problems

If printing fails with:

```text
Incorrect paper loaded (01 vs 11), aborting job!
```

check the following:

### 1. Correct Media Pack

Use matching Canon paper and ribbon cartridges.

Example:

```text
KP-36IP
```

### 2. Correct Cassette

Ensure the cassette is marked:

```text
Postcard
```

and matches the media pack.

### 3. Correct Driver Page Size

Verify:

```bash
lpoptions -p SELPHY_CP400 -l | grep PageSize
```

shows:

```text
*Postcard
```

### 4. Rebuild Gutenprint

If all settings are correct and the error persists, rebuild Gutenprint from source.

In testing, rebuilding Gutenprint resolved the "01 vs 11" media mismatch problem.

## Print a Test Page

Print the CUPS test page:

```bash
lp -d SELPHY_CP400 /usr/share/cups/data/testprint
```

If successful, the printer should begin feeding paper and printing immediately.

## Useful Commands

Show printer status:

```bash
lpstat -p -d
```

Show printer options:

```bash
lpoptions -p SELPHY_CP400
```

Show printer configuration:

```bash
lpstat -l -p SELPHY_CP400
```

Show recent CUPS errors:

```bash
tail -50 /var/log/cups/error_log
```

Both commands should complete without errors. Enable the camera stack (libcamera) in `raspi-config` if needed.


## Running the Application

Once the virtual environment has been activated:

```bash
python my_program.py
```

Replace `my_program.py` with the name of your application.

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


1) Install system packages (Raspberry Pi OS / Debian-like):

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-numpy ffmpeg libsndfile1 alsa-utils pulseaudio
```

Notes:
- `ffmpeg` and `libsndfile1` are useful/required for audio handling and some STT backends.
- On some Pi images `python3-picamera2` and `python3-opencv` are preferred from apt.

2) Install Python packages. A minimal install uses `requirements.txt`:

```bash
python3 -m pip install -r requirements.txt
```

The repository's `requirements.txt` includes core deps (picamera2, OpenCV, numpy)
and optional audio/STT packages. If you prefer to install audio/ASR packages
manually, run:

```bash
python3 -m pip install sounddevice soundfile SpeechRecognition
```

Optional: Whisper (local) for offline transcription
- Whisper provides good local transcription but requires PyTorch and can be
	large on disk. Install only if you need offline STT and have the resources:

```bash
python3 -m pip install -U openai-whisper
# Follow PyTorch install instructions for your platform: https://pytorch.org/get-started/locally/
```

Optional: Google GenAI (recommended for cloud transcription)
- If you'd like to use Google's GenAI transcription, install the Python SDK and
	set an API key in the environment. The package name and API surface may
	change over time; the instructions below reflect common usage.

```bash
python3 -m pip install google-generativeai
export GOOGLE_API_KEY="your-google-genai-api-key"
# or set GOOGLE_GENAI_API_KEY
```

The `main.py` will try Google GenAI transcription first when one of the
environment variables above is set, then fall back to Whisper (local) and
finally to the online Google SpeechRecognition adapter.

3) Run the app

```bash
python3 main.py          # normal camera preview
python3 main.py --voice  # capture one frame, record audio, transcribe, apply spoken commands
python3 main.py --voice --record-secs 6  # increase recording time
```

Audio / Microphone notes
- The `--voice` mode records from the default system microphone using
	`sounddevice`. Make sure ALSA/PulseAudio are configured and the microphone
	is available. Use `arecord -l` or `pactl list sources` to inspect devices.
- If `openai-whisper` is installed the code will try Whisper first (local).
	Otherwise it falls back to online Google recognition via `SpeechRecognition`.

Voice command examples
- Say simple commands like:
	- "grayscale" or "convert to grayscale"
	- "blur 7" (odd integer kernel)
	- "edges" or "canny"
	- "rotate 90" or "rotate -90"
	- "flip horizontal" or "flip vertical"
	- "resize 640x480"
	- "save processed.jpg"

Troubleshooting
- If `sounddevice` fails to open the microphone, ensure your user has access
	to ALSA/PulseAudio and test with `arecord`.
- Whisper requires a working PyTorch/ffmpeg setup; if transcription fails,
	the code prints errors and attempts the fallback.

Headless usage
- If you run on a headless Pi, either use a virtual display (Xvfb) or modify
	the code to save processed frames to disk or stream them elsewhere.

License / Notes
- See source files for usage and behavior. If you want, I can add a short
	troubleshooting section for common Pi microphone issues.