# Nanobanana Camera

A homage to the one made by [Nikbuild](https://github.com/nickbild/banamera)

This repository provides a small Python app that captures video from the
Raspberry Pi HQ Camera using `picamera2` and displays it in a desktop window
# Nanobanana Camera

A homage to the one made by [Nikbuild](https://github.com/nickbild/banamera)

This repository provides a small Python app that captures video from the
Raspberry Pi HQ Camera using `picamera2` and displays it in a desktop window
using OpenCV. It also includes an optional voice-command mode that records
microphone audio, transcribes it, and applies simple image-processing
commands to a captured frame.

Quick start

- Enable the camera stack (libcamera) in `raspi-config` if needed.

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