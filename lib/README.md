# lib/

Code shared between the two apps in this repo:

* [camera/](../camera/) — the original camera app: a live Picamera2 viewfinder, plus reviewing,
  printing, publishing, and voice-editing captured photos.
* [host/](../host/) — a camera-less companion app for a Sony camera's FTP photo transfer: it
  receives JPEGs over FTP and gives them the same reviewing/printing/publishing/voice-editing
  treatment, targeting a more constrained Raspberry Pi (e.g. a Zero W 2) with no camera attached.

Everything in here is camera-independent - it only ever operates on JPEG files already sitting on
disk, and draws through the `displays/` abstraction rather than assuming any particular hardware.
A bug fix here benefits both apps automatically.

## Contents

* `review_station.py` — `ReviewStationMixin`, the shared Play-mode/Publish/Speak/Print
  orchestration (browsing photos, the publish-destination flow, the hold-to-talk voice-edit
  review flow, submitting and watching a print job). Both apps' main class inherit from it; see
  the docstring at the top of the file for exactly what state a subclass needs to set up, and the
  three small hooks (`_capture_fresh_still`, `_non_play_menu`, `_empty_play_buttons`/
  `_empty_play_message`) that let a camera-less app opt out of the few genuinely camera-specific
  bits.
* `displays/` — the pluggable HDMI display + touch/mouse input backends (`create_display()`),
  used unchanged by both apps.
* `publishers/` — the pluggable Flickr/Bluesky/Custard Cream Server upload backends.
* `transcription/` — the pluggable Vosk/Gemini speech-to-text backends for the voice-edit prompt.
* `NanoBananaClient.py` — the Gemini ("Nano Banana") transcription + image-edit API client.
* `print_overlays.py` — watermark/date-stamp compositing for the copy sent to the printer.

## How it's imported

`lib/` isn't a pip-installed package - each app adds it to `sys.path` for itself at startup, since
it lives one directory above the app's own folder:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
```

After that, `import displays`, `import review_station`, etc. resolve normally, and the rest of
each app's code is unaware `lib/` is a separate folder at all. Each app still has its own
`requirements.txt`/venv, so the third-party packages these modules depend on (Pillow, google-genai,
vosk, flickrapi, atproto, requests, qrcode, pycups, ...) need installing in both.
