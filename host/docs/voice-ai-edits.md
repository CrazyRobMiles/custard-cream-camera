# Voice-Prompted AI Edits

While reviewing a received photo (see [Reviewing Received Photos](reviewing-photos.md)), hold **Speak**, say an editing instruction (e.g. "make it look like a watercolor painting"), and release. The app transcribes what you said, then shows you the transcript with three options before anything is sent anywhere for editing:

* **Send** — sends it, with the currently displayed image, to Google's Gemini ("Nano Banana") image model for editing.
* **Reject** — discards it. Nothing is sent for editing; you're back where you started.
* **Edit** — opens an on-screen keyboard to correct the text (misheard words, added detail, etc.), then returns to this same Send/Reject/Edit screen with the corrected text.

This review step exists because speech recognition isn't perfect, and a misheard instruction sent straight to an image-editing model wastes a request (and, depending on your Gemini plan, a quota unit) on a result you never wanted. Once sent, the result is saved to `captures/` as `ai_<timestamp>.jpg`, shown on screen for a few seconds, and becomes the new current selection. The app stays responsive while it's working since the network calls run on a background thread.

Transcription (turning your speech into the text prompt) is a **pluggable backend**, selected via `"transcribe_provider"` under `"custard_cream"` in [settings.json](../settings.json):

- **`"vosk"` (the shipped default)** — runs entirely on the device via a local [Vosk](https://alphacephei.com/vosk/) model, no network round-trip. Since it recognises speech live, the transcript is displayed on screen as you talk, updating word by word while **Speak** is still held. Implemented in [lib/transcription/vosk_transcriber.py](../../lib/transcription/vosk_transcriber.py).
- **`"gemini"`** — sends the whole recording to Gemini once you release **Speak**. No live text — just the "Recording... release to send" banner until it's done. Implemented in [lib/transcription/gemini_transcriber.py](../../lib/transcription/gemini_transcriber.py).

Both backends implement the same interface ([lib/transcription/base.py](../../lib/transcription/base.py)), selected by [lib/transcription/__init__.py](../../lib/transcription/__init__.py)'s `create_transcriber()` — the same plugin pattern used for [publishers](../../lib/publishers/) and [displays](../../lib/displays/). Image editing itself is unaffected by this choice and stays in [lib/NanoBananaClient.py](../../lib/NanoBananaClient.py). The whole flow (`start_voice_prompt()`/`finish_voice_prompt()`/`review_ai_prompt()`/`run_ai_edit()`/...) lives in [lib/review_station.py](../../lib/review_station.py), shared unchanged with the [camera app](../../camera/) — a fresh-capture branch used only by that app's physical shutter remote doesn't apply here, since this app never captures a photo itself.

On a Raspberry Pi Zero W 2 (this app's target), consider `"vosk"` over `"gemini"` for transcription if the network connection is unreliable, since it needs no round-trip at all - though the image-edit step itself always needs Gemini regardless.

## Setup

1. **Get a Gemini API key.** Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in with a Google account, and create a key. This is needed for image editing regardless of transcription backend, and for transcription itself if you use `"gemini"`.

2. **Make sure the SDKs are installed.** `google-genai` and `vosk` are both already in [requirements.txt](../requirements.txt), pulled in by the normal `pip install -r requirements.txt` venv setup.

3. **Set the API key as an environment variable.** `NanoBananaClient.py` reads it from `GOOGLE_API_KEY` by default (the variable name is itself configurable via `"api_key_env"` under `"custard_cream"` in settings.json) — deliberately *not* stored in `settings.json`, since that file is checked into git. For a quick one-off test from a terminal:
   ```bash
   export GOOGLE_API_KEY="your-api-key"
   ```
   For it to be set automatically every time the app runs (including from the desktop icon, with no terminal involved) see [Storing API Keys on the Device](api-keys.md).

4. **If using Vosk, download a model.** See [Installing Vosk](venv-setup.md#installing-vosk-local-speech-recognition) for the exact download/unzip commands and a one-liner to verify it loads. The default settings expect `vosk-model-small-en-us-0.15` (~40MB) unzipped to `models/vosk-model-small-en-us-0.15`, matching `"custard_cream.vosk.model_path"` in settings.json. **This is loaded once at app startup** (not on first Speak press) — a missing or wrong `model_path` will fail app startup entirely.

5. **Check the microphone.** Both backends need `arecord` (part of `alsa-utils`, normally already installed on Raspberry Pi OS — `sudo apt install alsa-utils` if not). Confirm it works standalone first:
   ```bash
   arecord -f S16_LE -r 16000 -c 1 -d 3 test.wav && aplay test.wav
   ```
   If you have multiple audio devices, set `"device"` under `"custard_cream"` in settings.json to the right ALSA device name (`arecord -l` lists them).

6. **Test it.** [Receive a photo over FTP](ftp-setup.md) first if you haven't - there's nothing to Speak over until at least one arrives. Then: hold **Speak**, say something like "make it look like a watercolor painting" (if using Vosk, watch the recognised text build up on screen as you talk), and release. The edited image should appear on screen and save to `captures/ai_<timestamp>.jpg`.

Recording length and the result's on-screen hold time are also configurable under `"custard_cream"` in settings.json. The Gemini model IDs (`transcribe_model`, `edit_model`) may need adjusting as Google's model naming evolves — check the current names in the [Gemini API docs](https://ai.google.dev/gemini-api/docs/models) if editing fails with a "model not found" style error.

## Diagnostics

Progress is shown on screen as well as logged. While a request is in flight, the banner shows what's actually happening: "Transcribing...", then "Sending image for processing...", then "Received result, saving..." — the same on-screen-diagnostics idea used for [printing](printing.md).

Every stage also prints a `Speak: ...` line to the terminal (or `custard_cream_camera_host.log`), so a stuck or failed edit can be narrowed down to exactly where it stopped.

Requests to Gemini time out after `"timeout_seconds"` (default `30`) under `"custard_cream"` in settings.json — without this, a stalled connection would hang indefinitely with no error. This only applies to work that goes over the network: image editing always, and transcription only when `"transcribe_provider"` is `"gemini"`.
