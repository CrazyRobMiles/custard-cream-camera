from .base import BaseTranscriber
from NanoBananaClient import AudioRecorder


class GeminiTranscriber(BaseTranscriber):
    """Records to a WAV file via arecord, then sends the whole clip to Gemini once
    the recording stops - no live partials, since Gemini only sees the finished clip.
    """

    def __init__(self, client_getter, audio_path, sample_rate=16000, channels=1,
                 max_record_seconds=15, device=None):
        self.client_getter = client_getter
        self.audio_path = audio_path
        self.recorder = AudioRecorder(
            sample_rate=sample_rate, channels=channels,
            max_seconds=max_record_seconds, device=device,
        )
        self.captured_path = None

    def start(self, on_partial=None):
        self.recorder.start(self.audio_path)

    def stop(self):
        self.captured_path = self.recorder.stop()
        if self.captured_path:
            print(f"Speak: recording stopped ({self.captured_path.stat().st_size} bytes)")
        return self.captured_path is not None

    def finalize(self):
        if self.captured_path is None:
            return None
        client = self.client_getter()
        return client.transcribe(self.captured_path.read_bytes())
