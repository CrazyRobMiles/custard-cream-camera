class BaseDisplay:
    """Common interface every display backend must implement."""

    def __init__(self, width=480, height=320):
        self.WIDTH = width
        self.HEIGHT = height
        self.quit_requested = False
        # Bumped by draw() every time it actually renders a frame - lets process_frame() tell
        # whether a button handler already repainted the screen this tick (many Play-mode
        # handlers - show_play_image(), show_publish_menu(), etc. - call draw() themselves)
        # before falling back to its own redraw, instead of always redrawing a second time.
        self.draw_count = 0

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
