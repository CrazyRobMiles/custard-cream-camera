# Voice-Prompted AI Edits

Choose a photo via the image browser (or use the shutter remote's speak key) and hold **Select** (or the remote button), say an editing instruction (e.g. "make it look like a watercolor painting"), and release — the app transcribes what you said and sends it with the chosen image to Google's Gemini ("Nano Banana") image model for editing. The result is saved to `captures/` as `ai_<timestamp>.jpg` and shown on screen for a few seconds. This is implemented in [custard_cream.py](../custard_cream.py); the viewfinder and other buttons stay responsive while it's working since the network calls run on a background thread.

## Setup

1. **Get a Gemini API key.** Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in with a Google account, and create a key. This is used for both speech transcription and image editing.

2. **Make sure the SDK is installed.** `google-genai` is already in [requirements.txt](../requirements.txt), so it's pulled in by the normal `pip install -r requirements.txt` venv setup — nothing extra needed unless your venv predates that being added.

3. **Set the API key as an environment variable.** `custard_cream.py` reads it from `GOOGLE_API_KEY` by default (the variable name is itself configurable via `"api_key_env"` under `"custard_cream"` in [settings.json](../settings.json)) — deliberately *not* stored in `settings.json`, since that file is checked into git:
   ```bash
   export GOOGLE_API_KEY="your-api-key"
   ```
   Run this before starting the app from a terminal.

   If you're launching from the [desktop icon](running-the-app.md) instead, this needs to be set before `run_magic_camera.sh` runs. Adding the `export` line to `~/.bashrc` is the usual suggestion, but a heads-up: `.desktop` files typically exec the script directly rather than through a login/interactive shell, so `~/.bashrc` doesn't always get sourced (behavior varies by desktop environment). The reliable way to check is to look at `magic_camera.log` after a desktop-icon launch — if the key isn't visible, you'll see `custard_cream.py`'s own clear error: `No API key found in environment variable 'GOOGLE_API_KEY'...`. If that happens, the most robust fix is adding the `export` line directly into `run_magic_camera.sh` itself, right after its `cd "$DIR"` line — that's guaranteed to run regardless of desktop environment quirks, since it's the script actually being executed.

4. **Check the microphone.** Needs `arecord` (part of `alsa-utils`, normally already installed on Raspberry Pi OS — `sudo apt install alsa-utils` if not). Confirm it works standalone first:
   ```bash
   arecord -f S16_LE -r 16000 -c 1 -d 3 test.wav && aplay test.wav
   ```
   If you have multiple audio devices, set `"device"` under `"custard_cream"` in settings.json to the right ALSA device name (`arecord -l` lists them) — it's `null` by default, which uses the system default input.

5. **Test it.** **Speak** opens the [image browser](image-browser.md) over photos already in `captures/` — it has no option to take a fresh one, so press **Click** first if you haven't taken any photos yet. Then: launch the app, tap **Speak**, tap a thumbnail to preview it, hold **Select**, say something like "make it look like a watercolor painting," and release. Watch the terminal (or `magic_camera.log`) for `Voice prompt: ...` — that confirms transcription worked; the edited image should then appear on screen and save to `captures/ai_<timestamp>.jpg`.

Recording length and the result's on-screen hold time are also configurable under `"custard_cream"` in settings.json. The model IDs (`transcribe_model`, `edit_model`) may need adjusting as Google's model naming evolves — check the current names in the [Gemini API docs](https://ai.google.dev/gemini-api/docs/models) if editing fails with a "model not found" style error.
