import tkinter as tk

from PIL import ImageDraw, ImageTk

from .base import BaseDisplay
from .widgets import ButtonPanel


class HDMIDesktopDisplay(BaseDisplay):
    """Displays frames in a plain window via Tkinter.

    No fullscreen mode-switching and no video driver selection - it just opens an ordinary
    window through whatever windowing system the desktop is already using, the same as any
    other desktop app. Simpler and more portable than HDMIPygameDisplay, at the cost of a
    little draw performance.
    """

    WIDTH = 480
    HEIGHT = 320

    def __init__(self, scale=1):
        super().__init__()

        self.scale = scale

        self.root = tk.Tk()
        self.root.title("Magic Camera")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", lambda event: self._on_close())

        self.label = tk.Label(self.root)
        self.label.pack()
        self.label.bind("<Button-1>", self._on_press)
        self.label.bind("<ButtonRelease-1>", self._on_release)

        self.buttons = ButtonPanel()
        self.photo_image = None

    def _on_close(self):
        self.quit_requested = True

    def _on_press(self, event):
        self.buttons.press(event.x / self.scale, event.y / self.scale)

    def _on_release(self, event):
        self.buttons.release(event.x / self.scale, event.y / self.scale)

    # ---------- BaseDisplay interface ----------

    def set_buttons(self, buttons):
        self.buttons.set_buttons(buttons)

    def update(self):
        self.root.update_idletasks()
        self.root.update()
        return self.buttons.update()

    def draw(self, img):
        draw = ImageDraw.Draw(img)
        self.buttons.draw(draw)

        if self.scale != 1:
            img = img.resize((int(self.WIDTH * self.scale), int(self.HEIGHT * self.scale)))

        # Keep a reference - Tkinter drops the image if it's garbage collected.
        self.photo_image = ImageTk.PhotoImage(img)
        self.label.configure(image=self.photo_image)

    def close(self):
        self.root.destroy()
