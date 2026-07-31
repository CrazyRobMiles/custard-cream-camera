# lib/

Supporting modules for [custard_cream_camera.py](../custard_cream_camera.py), kept in their own
folder to keep that file focused on the two home-screen setups (camera mode / FTP mode) rather than
growing to contain everything. `ftp_server.py` and `review_station.py` are the two biggest single
pieces of behavior the main app delegates out to, alongside the smaller pluggable-backend packages
below.

Everything in here (aside from `ftp_server.py`, which talks to the network) is camera-independent -
it only ever operates on JPEG files already sitting on disk, and draws through the `displays/`
abstraction rather than assuming any particular hardware.

## Contents

* `review_station.py` — `ReviewStationMixin`, the shared Play-mode/Publish/Speak/Print
  orchestration (browsing photos, the publish-destination flow, the hold-to-talk voice-edit
  review flow, submitting and watching a print job). `CustardCreamCamera` inherits from it; see
  the docstring at the top of the file for exactly what state a subclass needs to set up, and the
  three small hooks (`_capture_fresh_still`, `_non_play_menu`, `_empty_play_buttons`/
  `_empty_play_message`) that let FTP mode (no camera) opt out of the few genuinely
  camera-specific bits.
* `ftp_server.py` — `FTPReceiver`, the background FTP server used in FTP mode: receives JPEGs
  uploaded by a camera's FTP-transfer feature and hands each one to the main app as it completes,
  via a thread-safe queue.
* `displays/` — the pluggable HDMI display + touch/mouse input backends (`create_display()`).
* `publishers/` — the pluggable Flickr/Bluesky/Custard Cream Server upload backends.
* `transcription/` — the pluggable Vosk/Gemini speech-to-text backends for the voice-edit prompt.
* `NanoBananaClient.py` — the Gemini ("Nano Banana") transcription + image-edit API client.
* `print_overlays.py` — watermark/date-stamp compositing for the copy sent to the printer.

## How it's imported

`lib/` isn't a pip-installed package - `custard_cream_camera.py` adds it to `sys.path` for itself
at startup, since it lives right next to the app's own folder:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
```

After that, `import displays`, `import review_station`, etc. resolve normally, and the rest of the
app's code is unaware `lib/` is a separate folder at all.
