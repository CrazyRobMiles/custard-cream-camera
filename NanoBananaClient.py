import os
import signal
import subprocess
from pathlib import Path

from google import genai
from google.genai import types


class CustardCreamClient:
    """Wraps the Google GenAI SDK for speech-to-text and Nano Banana image editing."""

    def __init__(self, api_key_env="GOOGLE_API_KEY", transcribe_model="gemini-2.5-flash",
                 edit_model="gemini-2.5-flash-image", timeout_seconds=30):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"No API key found in environment variable '{api_key_env}'. Get one from "
                f"https://aistudio.google.com/apikey and set it before running, e.g. "
                f"export {api_key_env}=..."
            )
        # Without an explicit timeout, a stalled connection (flaky wifi, a network path that
        # silently drops packets, etc.) hangs the request forever with no error at all - ai_pending
        # would stay stuck, and there'd be no diagnostic to explain why. This turns that into a
        # bounded, clearly-reported failure instead.
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_seconds * 1000))
        self.transcribe_model = transcribe_model
        self.edit_model = edit_model

    def transcribe(self, audio_bytes, mime_type="audio/wav"):
        print(f"Speak: sending {len(audio_bytes)} bytes to '{self.transcribe_model}' for transcription")
        response = self.client.models.generate_content(
            model=self.transcribe_model,
            contents=[
                "Transcribe the spoken words in this audio clip. Reply with only the "
                "transcription, no extra commentary.",
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
        )
        text = (response.text or "").strip()
        if text:
            print(f"Speak: transcription result: {text!r}")
        else:
            print("Speak: transcription returned no text")
        return text or None

    def edit_image(self, image_bytes, prompt_text, mime_type="image/jpeg"):
        print(f"Speak: sending {len(image_bytes)} bytes to '{self.edit_model}' for editing (prompt: {prompt_text!r})")
        response = self.client.models.generate_content(
            model=self.edit_model,
            contents=[
                prompt_text,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
        )
        # Response shape (candidates[0].content.parts, each either text or inline_data) matches
        # the documented Gemini image-generation output as of the google-genai SDK this was
        # written against - worth double-checking against current docs if this stops matching.
        text_parts = []
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                print(f"Speak: edit response contained image data ({len(part.inline_data.data)} bytes)")
                return part.inline_data.data
            if part.text:
                text_parts.append(part.text)

        if text_parts:
            # The model sometimes explains itself in text instead of returning an image (e.g. a
            # safety refusal, or asking for a clearer prompt) - surfacing it here is the only way
            # to see why, since the caller just gets back None either way.
            print(f"Speak: edit response contained no image, only text: {' '.join(text_parts)!r}")
        else:
            print("Speak: edit response contained no image and no text")
        return None


class AudioRecorder:
    """Records audio via `arecord` (ALSA) - no extra Python audio dependency needed."""

    def __init__(self, sample_rate=16000, channels=1, max_seconds=15, device=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_seconds = max_seconds
        self.device = device
        self.process = None
        self.path = None

    def start(self, path):
        self.path = Path(path)
        args = [
            "arecord",
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-d", str(self.max_seconds),
        ]
        if self.device:
            args += ["-D", self.device]
        args.append(str(self.path))

        self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self, timeout=5):
        """Stops recording and returns the path to the recorded clip, or None if nothing usable was captured."""
        if self.process is None:
            return None

        if self.process.poll() is None:
            # SIGINT (not terminate/SIGTERM) is what arecord expects to finalize the WAV
            # header cleanly - the same signal sent when you Ctrl+C it in a terminal.
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        self.process = None

        if self.path.exists() and self.path.stat().st_size > 1024:
            return self.path
        return None
