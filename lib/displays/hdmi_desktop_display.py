import io
import tkinter as tk

from PIL import ImageDraw

from .base import BaseDisplay
from .widgets import ButtonPanel


class HDMIDesktopDisplay(BaseDisplay):
    """Displays frames in a window via Tkinter (fullscreen by default).

    Just opens an ordinary window through whatever windowing system the desktop is already
    using, the same as any other desktop app.
    """

    def __init__(self, fullscreen=True, scale=1, width=480, height=320):
        super().__init__(width, height)

        self.root = tk.Tk()
        self.root.title("Custard Cream Camera")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", lambda event: self._on_close())
        self.root.configure(bg="black")

        if fullscreen:
            # On the very first launch after the desktop session has just started, the window
            # manager can still be getting itself set up and silently drops a fullscreen
            # request made before it has finished managing the window - the app then shows up
            # small, and only goes fullscreen on a later run once the WM has settled. Forcing
            # the window to exist (update_idletasks) before asking for fullscreen, and
            # re-asserting it shortly after, works around that race.
            self.root.update_idletasks()
            self.root.attributes("-fullscreen", True)
            self.root.after(250, lambda: self.root.attributes("-fullscreen", True))
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            self.scale = min(screen_w / self.WIDTH, screen_h / self.HEIGHT)
        else:
            self.scale = scale

        # place() rather than pack(): centers the (possibly letterboxed) image within the
        # window regardless of whether the window is the image's own size (windowed mode)
        # or the whole screen (fullscreen), with no offset math needed for click handling -
        # event.x/event.y are already relative to the label's own top-left corner.
        self.label = tk.Label(self.root, bg="black", bd=0, highlightthickness=0)
        self.label.place(relx=0.5, rely=0.5, anchor="center")
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
        self.draw_count += 1

        # Copy before drawing buttons on - callers (e.g. self.play_view) keep their own
        # reference to img and redraw it again later; drawing buttons directly onto it would
        # permanently stamp that button set into the stored image itself.
        img = img.copy()
        draw = ImageDraw.Draw(img)
        self.buttons.draw(draw)

        if self.scale != 1:
            img = img.resize((int(self.WIDTH * self.scale), int(self.HEIGHT * self.scale)))

        # Hand Tkinter a raw PPM buffer instead of going through PIL's ImageTk: on Debian/
        # Raspberry Pi OS that's a separate apt package (python3-pil.imagetk) from python3-tk,
        # and this way there's nothing extra to install - just core Pillow + stdlib Tkinter.
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PPM")

        # Keep a reference - Tkinter drops the image if it's garbage collected.
        self.photo_image = tk.PhotoImage(data=buf.getvalue(), format="ppm")
        self.label.configure(image=self.photo_image)

    def close(self):
        self.root.destroy()
