import sys

import pygame
from PIL import ImageDraw

from .base import BaseDisplay
from .widgets import ButtonPanel


class HDMIPygameDisplay(BaseDisplay):
    """Displays frames fullscreen via SDL/pygame, using the mouse for touch input.

    Bypasses the desktop's own window manager for a dedicated, lower-overhead fullscreen
    surface, at the cost of needing a working SDL video driver (X11/Wayland/KMSDRM) for
    your particular setup - see HDMIDesktopDisplay for a plain-window alternative.
    """

    def __init__(self, fullscreen=True, window_width=800, window_height=480, width=480, height=320):
        super().__init__(width, height)

        pygame.init()
        pygame.mouse.set_visible(not fullscreen)

        flags = pygame.FULLSCREEN if fullscreen else 0
        # Fullscreen requests an exclusive mode change to the given size; if the display
        # doesn't support that exact mode, SDL can silently keep the desktop's current mode
        # instead. (0, 0) tells it to use the desktop's current resolution instead.
        size = (0, 0) if fullscreen else (window_width, window_height)
        self.surface = pygame.display.set_mode(size, flags)
        pygame.display.set_caption("Custard Cream Camera")

        driver = pygame.display.get_driver()
        print(f"HDMIPygameDisplay: SDL video driver '{driver}', surface size {self.surface.get_size()}")
        if driver == "dummy":
            print(
                "HDMIPygameDisplay: SDL fell back to the 'dummy' driver, so nothing will actually "
                "appear on screen. This usually means DISPLAY/WAYLAND_DISPLAY wasn't visible "
                "to this process - common if it was launched with `sudo` (which clears the "
                "environment) or over SSH without a graphical session attached. Try running "
                "without sudo from a terminal on the Pi's own desktop, or use `sudo -E` if "
                "root is required.",
                file=sys.stderr,
            )

        self.buttons = ButtonPanel()
        self._update_scaling()

    def _update_scaling(self):
        surface_w, surface_h = self.surface.get_size()
        self.scale = min(surface_w / self.WIDTH, surface_h / self.HEIGHT)
        self.scaled_size = (int(self.WIDTH * self.scale), int(self.HEIGHT * self.scale))
        self.offset = (
            (surface_w - self.scaled_size[0]) // 2,
            (surface_h - self.scaled_size[1]) // 2,
        )

    def _window_to_logical(self, pos):
        x = (pos[0] - self.offset[0]) / self.scale
        y = (pos[1] - self.offset[1]) / self.scale
        return x, y

    # ---------- BaseDisplay interface ----------

    def set_buttons(self, buttons):
        self.buttons.set_buttons(buttons)

    def update(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit_requested = True
            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, y = self._window_to_logical(event.pos)
                self.buttons.press(x, y)
            elif event.type == pygame.MOUSEBUTTONUP:
                x, y = self._window_to_logical(event.pos)
                self.buttons.release(x, y)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.quit_requested = True

        return self.buttons.update()

    def draw(self, img):
        draw = ImageDraw.Draw(img)
        self.buttons.draw(draw)

        img = img.convert("RGB")
        frame = pygame.image.frombuffer(img.tobytes(), img.size, "RGB")
        frame = pygame.transform.smoothscale(frame, self.scaled_size)

        self.surface.fill((0, 0, 0))
        self.surface.blit(frame, self.offset)
        pygame.display.flip()

    def close(self):
        pygame.quit()
