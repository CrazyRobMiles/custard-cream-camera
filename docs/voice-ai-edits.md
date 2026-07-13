# Voice-Prompted AI Edits

Choose a photo via the image browser (or use the shutter remote's speak key) and hold **Select** (or the remote button), say an editing instruction (e.g. "make it look like a watercolor painting"), and release — the app transcribes what you said and sends it with the chosen image to Google's Gemini ("Nano Banana") image model for editing. The result is saved to `captures/` as `ai_<timestamp>.jpg` and shown on screen for a few seconds. This is implemented in [custard_cream.py](../custard_cream.py); the viewfinder and other buttons stay responsive while it's working since the network calls run on a background thread.

Requirements:

* A microphone, and `arecord` available (part of `alsa-utils`, normally already installed on Raspberry Pi OS — `sudo apt install alsa-utils` if not).
* A Gemini API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey), set as an environment variable **before launching the app** (not stored in `settings.json`, since that file is checked into git):
  ```bash
  export GOOGLE_API_KEY="your-api-key"
  ```
  If launching from a desktop icon, add the `export` line to `~/.bashrc` (or wherever your shell profile lives) so it's set before `run_magic_camera.sh` runs.

Model names, recording length, and the result's on-screen hold time are all configurable under `"custard_cream"` in [settings.json](../settings.json). The model IDs (`transcribe_model`, `edit_model`) may need adjusting as Google's model naming evolves — check the current names in the [Gemini API docs](https://ai.google.dev/gemini-api/docs/models) if editing fails with a "model not found" style error.
