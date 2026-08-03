# Voice-Prompted AI Edits

How you provide the editing instruction is controlled by `"input_method"` under `"ai_edit"` in
[settings.json](../settings.json.example) — `"voice"` (the default, described first below) or
`"keyboard"` (preset prompts plus a custom on-screen keyboard entry, see
[Keyboard/Preset Input](#keyboardpreset-input) further down). Setting `"ai_edit.enabled"` to
`false` removes AI editing entirely — no button in Play mode, and (camera mode) no shutter-remote
speak-key binding either — useful for a device that only needs to receive/print/publish photos,
e.g. a low-spec Pi Zero-class image receiver.

## Voice input (`ai_edit.input_method`: `"voice"`, the default)

In Play mode (see [Home Screen: Camera Mode vs FTP Mode](home-screen-modes.md)), hold **Speak** (or, in camera mode, use the shutter remote's speak key, which works from any mode), say an editing instruction (e.g. "make it look like a watercolor painting"), and release. The app transcribes what you said, then shows you the transcript with three options before anything is sent anywhere for editing:

* **Send** — sends it, with the currently displayed image, to Google's Gemini ("Nano Banana") image model for editing.
* **Reject** — discards it. Nothing is sent for editing; you're back where you started.
* **Edit** — opens an on-screen keyboard to correct the text (misheard words, added detail, etc.), then returns to this same Send/Reject/Edit screen with the corrected text.

This review step exists because speech recognition isn't perfect, and a misheard instruction sent straight to an image-editing model wastes a request (and, depending on your Gemini plan, a quota unit) on a result you never wanted. Once sent, the result is saved to `captures/` as `ai_<timestamp>.jpg`, shown on screen for a few seconds, and becomes the new current selection. Image editing always goes through Gemini; the app stays responsive while it's working since the network calls run on a background thread.

Transcription (turning your speech into the text prompt) is a **pluggable backend**, selected via `"transcribe_provider"` under `"custard_cream"` in [settings.json](../settings.json.example) — this setting only matters when `"ai_edit.input_method"` is `"voice"`:

- **`"vosk"` (the shipped default)** — runs entirely on the device via a local [Vosk](https://alphacephei.com/vosk/) model, no network round-trip. Since it recognises speech live, the transcript is displayed on screen as you talk, updating word by word while **Speak** is still held. Implemented in [lib/transcription/vosk_transcriber.py](../lib/transcription/vosk_transcriber.py).
- **`"gemini"`** — sends the whole recording to Gemini once you release **Speak**. No live text — just the "Recording... release to send" banner until it's done. Implemented in [lib/transcription/gemini_transcriber.py](../lib/transcription/gemini_transcriber.py).

Both backends implement the same interface ([lib/transcription/base.py](../lib/transcription/base.py)), selected by [lib/transcription/__init__.py](../lib/transcription/__init__.py)'s `create_transcriber()` — the same plugin pattern used for [publishers](../lib/publishers/) and [displays](../lib/displays/). Image editing itself is unaffected by this choice and stays in [lib/NanoBananaClient.py](../lib/NanoBananaClient.py). The whole flow (`start_voice_prompt()`/`finish_voice_prompt()`/`review_ai_prompt()`/`run_ai_edit()`/...) lives in [lib/review_station.py](../lib/review_station.py) — the fresh-capture branch it falls back to only matters in camera mode, since an FTP-mode device never captures a photo itself.

On a lower-powered device (e.g. a Pi Zero W 2 running in FTP mode), consider `"vosk"` over `"gemini"` for transcription if the network connection is unreliable, since it needs no round-trip at all - though the image-edit step itself always needs Gemini regardless.

## Keyboard/Preset Input

Set `"ai_edit.input_method"` to `"keyboard"` for a device with no microphone, or where speech
recognition simply isn't wanted (e.g. a low-spec Pi Zero-class image receiver/printer, where a
local Vosk model is too much for the hardware - see below). The Play-mode button becomes **AI
Edit** (a normal tap, not hold-to-talk) instead of **Speak**:

* Tapping it shows a grid of the prompts configured under `"ai_edit.presets"` in settings.json (any
  number, not just four - laid out two per row), plus **Custom...** and **Back**.
* Picking a preset, or **Custom...** (which opens the same on-screen keyboard **Edit** uses in the
  voice flow above, starting blank), lands on the same Send/Reject/Edit confirm screen described
  above - so a preset or typed prompt can still be tweaked or rejected before it's sent to Gemini.
* **Back** returns to Play mode without choosing anything.

Crucially, no transcriber is created at all in this mode (nor when `"ai_edit.enabled"` is
`false`): `"transcribe_provider"`/`"vosk"` in settings.json are simply not read, the `vosk` package
is never imported, and no Vosk model is loaded into memory - important on something like a Pi Zero,
where even a "small" ~40MB model is a real cost you don't want to pay if voice input is never used.
In camera mode, the shutter remote's speak key is also left unbound in this case, since it exists
purely to drive hold-to-talk.

## Setup

Steps 1 and 3 (the Gemini API key) apply regardless of `"ai_edit.input_method"`, since image
editing always goes through Gemini. Steps 2, 4, and 5 only matter for `"input_method": "voice"` —
skip them entirely for `"keyboard"` (or `"ai_edit.enabled": false`).

1. **Get a Gemini API key.** Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in with a Google account, and create a key. This is needed for image editing regardless of transcription backend, and for transcription itself if you use `"gemini"`.

2. **Make sure the SDKs are installed.** `google-genai` is already in [requirements.txt](../requirements.txt), pulled in by the normal `pip install -r requirements.txt` venv setup. `vosk` is kept in its own [requirements-vosk.txt](../requirements-vosk.txt) instead (see [Setting Up the Python Virtual Environment](venv-setup.md)), since it's a real install/memory cost not worth paying on a device that never uses voice input — install it with `pip install -r requirements-vosk.txt` if you're using `"vosk"` as the provider.

3. **Set the API key as an environment variable.** `NanoBananaClient.py` reads it from `GOOGLE_API_KEY` by default (the variable name is itself configurable via `"api_key_env"` under `"custard_cream"` in settings.json) — deliberately *not* stored in `settings.json`, since that file is checked into git. For a quick one-off test from a terminal:
   ```bash
   export GOOGLE_API_KEY="your-api-key"
   ```
   For it to be set automatically every time the app runs (including from the desktop icon, with no terminal involved) see [Storing API Keys on the Device](api-keys.md).

4. **If using Vosk, download a model.** See [Installing Vosk](venv-setup.md#installing-vosk-local-speech-recognition) for the exact download/unzip commands and a one-liner to verify it loads. The default settings expect `vosk-model-small-en-us-0.15` (~40MB) unzipped to `models/vosk-model-small-en-us-0.15`, matching `"custard_cream.vosk.model_path"` in settings.json — adjust that setting if you use a different model or location. **This is loaded once at app startup** (not on first Speak press, to avoid a delay on first use) — a missing or wrong `model_path` will fail app startup entirely, not just the Speak feature, so get this right before relying on Vosk as the active provider.

5. **Check the microphone.** Both backends need `arecord` (part of `alsa-utils`, normally already installed on Raspberry Pi OS — `sudo apt install alsa-utils` if not). Confirm it works standalone first:
   ```bash
   arecord -f S16_LE -r 16000 -c 1 -d 3 test.wav && aplay test.wav
   ```
   If you have multiple audio devices, set `"device"` under `"custard_cream"` in settings.json to the right ALSA device name (`arecord -l` lists them) — it's `null` by default, which uses the system default input. This is shared by both transcription backends, since it's a property of the physical mic, not the transcriber.

6. **Test it.** Play mode has no option to take a fresh photo, so make sure at least one photo exists first — in camera mode, press **Click** (in Capture mode); in FTP mode, [receive a photo over FTP](ftp-setup.md). Then: hold **Speak**, say something like "make it look like a watercolor painting" (if using Vosk, watch the recognised text build up on screen as you talk), and release. The edited image should then appear on screen and save to `captures/ai_<timestamp>.jpg`.

Recording length and the result's on-screen hold time are also configurable under `"custard_cream"` in settings.json. The Gemini model IDs (`transcribe_model`, `edit_model`) may need adjusting as Google's model naming evolves — check the current names in the [Gemini API docs](https://ai.google.dev/gemini-api/docs/models) if editing (or Gemini-backend transcription) fails with a "model not found" style error.

## Diagnostics

Progress is shown on screen as well as logged. While a request is in flight, the banner that would otherwise just say "Processing..." instead shows what's actually happening: "Transcribing...", then (once you've reviewed and sent the prompt) "Sending image for processing...", then "Received result, saving..." — the same on-screen-diagnostics idea used for [printing](printing.md), applied to this workflow.

Every stage also prints a `Speak: ...` line to the terminal (or `custard_cream_camera.log`), so a stuck or failed edit can be narrowed down to exactly where it stopped: recording start/stop, transcription (whichever backend is active) and its result, whether the prompt was sent/rejected at the review step, the request sent for image editing, and the response received (including any text the model returned instead of an image, e.g. a safety refusal — normally invisible on screen, since the caller only ever sees `None`).

Requests to Gemini time out after `"timeout_seconds"` (default `30`) under `"custard_cream"` in settings.json — without this, a stalled connection (flaky wifi, a network path that silently drops packets) would hang indefinitely with no error and no diagnostic output at all. This only applies to work that actually goes over the network: image editing always, and transcription only when `"transcribe_provider"` is `"gemini"` — Vosk transcription is local and isn't affected by connectivity at all. If a Gemini-backed request hangs repeatedly even with a normally-reliable connection, try raising `"timeout_seconds"` in case it's just Gemini being slow rather than the connection actually stalling.
