import json
import subprocess
from threading import Thread

import vosk

from .base import BaseTranscriber

vosk.SetLogLevel(-1)  # Vosk's native logging is verbose enough to drown out the
                       # Speak: ... diagnostic lines this codebase relies on.


class VoskTranscriber(BaseTranscriber):
    """Streams microphone audio through a local Vosk model via arecord, producing
    live partial transcripts as speech is recognised - no network round-trip.
    """

    def __init__(self, model_path, sample_rate=16000, channels=1, device=None,
                 max_record_seconds=15):
        try:
            self.model = vosk.Model(model_path)
        except Exception as e:
            raise RuntimeError(
                f"Could not load Vosk model from '{model_path}': {e}. Download a model "
                f"(e.g. vosk-model-small-en-us-0.15) from https://alphacephei.com/vosk/models, "
                f"unzip it, and point \"custard_cream.vosk.model_path\" at the unzipped folder."
            ) from e
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self.max_record_seconds = max_record_seconds
        self.process = None
        self.reader_thread = None
        self.recognizer = None
        self.final_text = None

    def start(self, on_partial=None):
        self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
        self.final_text = None
        # AcceptWaveform() returns True whenever Vosk hits an internal pause/segment
        # boundary mid-recording, not just at stop() - each such boundary finalizes
        # and clears the recognizer's buffer via Result(). Segments already shown via
        # on_partial() must be accumulated here, since a lone FinalResult() at stop()
        # only covers audio since the *last* boundary - it can be empty even though
        # plenty was already recognized, wrongly reading as "no audio captured".
        self._segments = []
        args = [
            "arecord",
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-t", "raw",
            "-d", str(self.max_record_seconds),
        ]
        if self.device:
            args += ["-D", self.device]

        self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.reader_thread = Thread(target=self._read_loop, args=(on_partial,), daemon=True)
        self.reader_thread.start()

    def _read_loop(self, on_partial):
        chunk_size = 4000
        stdout = self.process.stdout
        last_shown = None
        while True:
            data = stdout.read(chunk_size)
            if not data:
                break
            if self.recognizer.AcceptWaveform(data):
                segment = json.loads(self.recognizer.Result()).get("text", "")
                if segment:
                    self._segments.append(segment)
                trailing = ""
            else:
                trailing = json.loads(self.recognizer.PartialResult()).get("partial", "")

            shown = " ".join(self._segments + ([trailing] if trailing else []))
            if shown and shown != last_shown and on_partial:
                on_partial(shown)
                last_shown = shown

    def stop(self, timeout=5):
        """Stops capturing (fast, local only) and returns whether any usable audio
        was captured. Safe to call even if nothing is currently recording.
        """
        if self.process is None:
            return False

        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        stderr = self.process.stderr.read().decode(errors="replace").strip() if self.process.stderr else ""
        self.process = None

        # Killing arecord closes its stdout, which unblocks the reader thread's
        # blocking read() with EOF - bounded join as a safety net regardless.
        if self.reader_thread is not None:
            self.reader_thread.join(timeout=timeout)
            self.reader_thread = None

        # Only safe to ask for the final result once the reader thread has fed it
        # every buffered chunk - asking earlier can lose the tail of the utterance.
        # This only covers audio since the last mid-recording segment boundary (see
        # the note in start()) - segments finalized earlier are already in self._segments
        # and must be included too, or a recording with any pause in it can wrongly
        # come back empty despite having recognised text throughout.
        trailing = json.loads(self.recognizer.FinalResult()).get("text", "").strip()
        if trailing:
            self._segments.append(trailing)
        self.final_text = " ".join(self._segments).strip() or None

        if self.final_text:
            print(f"Speak: Vosk transcription result: {self.final_text!r}")
        else:
            reason = f": {stderr}" if stderr else ""
            print(f"Speak: Vosk transcription returned no text{reason}")
        return self.final_text is not None

    def finalize(self):
        return self.final_text
