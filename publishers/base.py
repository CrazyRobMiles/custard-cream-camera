class BasePublisher:
    """Common interface every publish backend must implement."""

    name = "publisher"

    def publish(self, image_path, tags=None):
        """Uploads/posts image_path (a Path). Returns True on success, False on failure - or
        raises, which callers should catch and treat the same as a False return.
        """
        raise NotImplementedError
