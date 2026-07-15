class BaseTranscriber:
    """Common interface every transcription backend must implement.

    start()/stop()/finalize() bracket one hold-to-talk gesture:
      - start() begins capturing audio (and, for streaming backends, transcribing
        live). If given, on_partial(text) is called with interim transcripts as
        they arrive - streaming backends (e.g. Vosk) call it repeatedly, batch
        backends (e.g. Gemini) never call it. It runs on a background thread, so
        it must never touch Picamera2/pygame/the screen directly - same contract
        as the ai_prompt_ready/ai_prompt_text pattern it feeds into.
      - stop() stops capturing. Fast and local-only, safe to call from the main
        thread. Returns whether any usable audio was captured. Must be a safe
        no-op if called with no recording in progress.
      - finalize() returns the final transcript text, or None. May block on
        network I/O, so callers must run it on a background thread.
    """

    def start(self, on_partial=None):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def finalize(self):
        raise NotImplementedError
