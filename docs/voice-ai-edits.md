# Voice-Prompted AI Edits

In [Play mode](capture-and-play-modes.md), hold **Speak** (or use the shutter remote's speak key, which works from any mode), say an editing instruction (e.g. "make it look like a watercolor painting"), and release — the app transcribes what you said and sends it with the currently displayed image to Google's Gemini ("Nano Banana") image model for editing. The result is saved to `captures/` as `ai_<timestamp>.jpg`, shown on screen for a few seconds, and becomes the new current selection in Play mode. This is implemented in [NanoBananaClient.py](../NanoBananaClient.py); the viewfinder and other buttons stay responsive while it's working since the network calls run on a background thread.

## Setup

1. **Get a Gemini API key.** Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in with a Google account, and create a key. This is used for both speech transcription and image editing.

2. **Make sure the SDK is installed.** `google-genai` is already in [requirements.txt](../requirements.txt), so it's pulled in by the normal `pip install -r requirements.txt` venv setup — nothing extra needed unless your venv predates that being added.

3. **Set the API key as an environment variable.** `NanoBananaClient.py` reads it from `GOOGLE_API_KEY` by default (the variable name is itself configurable via `"api_key_env"` under `"custard_cream"` in [settings.json](../settings.json)) — deliberately *not* stored in `settings.json`, since that file is checked into git. For a quick one-off test from a terminal:
   ```bash
   export GOOGLE_API_KEY="your-api-key"
   ```
   For it to be set automatically every time the app runs (including from the desktop icon, with no terminal involved) see [Storing API Keys on the Device](api-keys.md).

4. **Check the microphone.** Needs `arecord` (part of `alsa-utils`, normally already installed on Raspberry Pi OS — `sudo apt install alsa-utils` if not). Confirm it works standalone first:
   ```bash
   arecord -f S16_LE -r 16000 -c 1 -d 3 test.wav && aplay test.wav
   ```
   If you have multiple audio devices, set `"device"` under `"custard_cream"` in settings.json to the right ALSA device name (`arecord -l` lists them) — it's `null` by default, which uses the system default input.

5. **Test it.** [Play mode](capture-and-play-modes.md) has no option to take a fresh photo, so press **Click** first (in Capture mode) if you haven't taken any yet. Then: launch the app, tap **Play**, hold **Speak**, say something like "make it look like a watercolor painting," and release. The edited image should then appear on screen and save to `captures/ai_<timestamp>.jpg`.

Recording length and the result's on-screen hold time are also configurable under `"custard_cream"` in settings.json. The model IDs (`transcribe_model`, `edit_model`) may need adjusting as Google's model naming evolves — check the current names in the [Gemini API docs](https://ai.google.dev/gemini-api/docs/models) if editing fails with a "model not found" style error.

## Diagnostics

Every stage prints a `Speak: ...` line to the terminal (or `custard_cream_camera.log`), so a stuck or failed edit can be narrowed down to exactly where it stopped: recording start/stop (with the captured file size), which photo is being used, the request sent for transcription and its result, the request sent for image editing, and the response received (including any text the model returned instead of an image, e.g. a safety refusal — normally invisible, since the caller only ever sees `None`).

Requests to Gemini time out after `"timeout_seconds"` (default `30`) under `"custard_cream"` in settings.json — without this, a stalled connection (flaky wifi, a network path that silently drops packets) would hang indefinitely with no error and no diagnostic output at all, which is exactly what "stuck after sending for transcription" with no further `Speak:` lines indicates. If it happens repeatedly even with a normally-reliable connection, try raising `"timeout_seconds"` in case it's just Gemini being slow rather than the connection actually stalling.
