class BaseDisplay:
    """Common interface every display backend must implement."""

    def __init__(self, width=480, height=320):
        self.WIDTH = width
        self.HEIGHT = height
        self.quit_requested = False

    def set_buttons(self, buttons):
        raise NotImplementedError

    def draw(self, img):
        """Render a 480x320 landscape PIL image (with any button overlay) to the display."""
        raise NotImplementedError

    def update(self):
        """Apply any pending input (touch/mouse/keyboard). Returns True if a redraw is needed."""
        return False

    def close(self):
        pass
