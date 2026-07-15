import tempfile
from pathlib import Path

from .base import BaseTranscriber


def create_transcriber(settings, client_getter):
    """Instantiate the transcription backend selected by
    settings["custard_cream"]["transcribe_provider"]."""

    custard_cream_settings = settings.get("custard_cream", {})
    provider = custard_cream_settings.get("transcribe_provider", "gemini")

    if provider == "vosk":
        from .vosk_transcriber import VoskTranscriber
        return VoskTranscriber(
            sample_rate=custard_cream_settings.get("sample_rate", 16000),
            channels=custard_cream_settings.get("channels", 1),
            device=custard_cream_settings.get("device"),
            max_record_seconds=custard_cream_settings.get("max_record_seconds", 15),
            **custard_cream_settings.get("vosk", {}),
        )

    if provider == "gemini":
        from .gemini_transcriber import GeminiTranscriber
        return GeminiTranscriber(
            client_getter=client_getter,
            audio_path=Path(tempfile.gettempdir()) / "custard_cream_camera_prompt.wav",
            sample_rate=custard_cream_settings.get("sample_rate", 16000),
            channels=custard_cream_settings.get("channels", 1),
            max_record_seconds=custard_cream_settings.get("max_record_seconds", 15),
            device=custard_cream_settings.get("device"),
        )

    raise ValueError(f"Unknown custard_cream.transcribe_provider: {provider!r}")


__all__ = ["BaseTranscriber", "create_transcriber"]
