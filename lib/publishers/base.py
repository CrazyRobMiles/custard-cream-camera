class BasePublisher:
    """Common interface every publish backend must implement."""

    name = "publisher"
    # Short label for the narrow (110px) Publish-menu buttons - full display names don't fit.
    button_text = "Publish"

    def publish(self, image_path, tags=None, ai_instruction=None):
        """Uploads/posts image_path (a Path). Returns True on success, False on failure - or
        raises, which callers should catch and treat the same as a False return.

        ai_instruction is the voice-edit prompt that produced image_path, if any (None for a
        plain, non-AI-edited photo) - only custard_cream_server currently does anything with it.
        """
        raise NotImplementedError
