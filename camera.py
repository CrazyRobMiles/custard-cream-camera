import time
import sys
import termios
import tty
import select
from pathlib import Path

import numpy as np
from picamera2 import Picamera2
from PIL import Image, ImageDraw, ImageFont

from ili9486_fullscreen import ILI9486FullScreen


# ------------------------------------------------------------
# Keyboard handling (non-blocking)
# ------------------------------------------------------------

class Keyboard:
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

    def get_key(self):
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def close(self):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


# ------------------------------------------------------------
# Fast NumPy RGB888 → RGB565
# ------------------------------------------------------------

def rgb888_to_rgb565_numpy(img: Image.Image) -> bytes:
    arr = np.asarray(img, dtype=np.uint8)

    r = (arr[:, :, 0] >> 3).astype(np.uint16)
    g = (arr[:, :, 1] >> 2).astype(np.uint16)
    b = (arr[:, :, 2] >> 3).astype(np.uint16)

    rgb565 = (r << 11) | (g << 5) | b
    return rgb565.byteswap().tobytes()  # big-endian


# ------------------------------------------------------------
# Display + Camera setup
# ------------------------------------------------------------

lcd = ILI9486FullScreen(
    dc_pin=24,
    reset_pin=25,
    spi_speed=12_000_000   # safe speed; try 16MHz later
)

lcd.clear((0, 0, 0))


picam2 = Picamera2()

camera_config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "RGB888"},
    controls={
        "FrameRate": 30
    }
)

picam2.configure(camera_config)
picam2.start()
time.sleep(0.5)


# ------------------------------------------------------------
# Runtime state
# ------------------------------------------------------------

kbd = Keyboard()
frame_count = 0
fps = 0
fps_timer = time.time()
last_fps_update = time.time()

save_dir = Path("captures")
save_dir.mkdir(exist_ok=True)

print("Controls: SPACE = shutter, Q = quit")


# ------------------------------------------------------------
# Main loop
# ------------------------------------------------------------

try:
    while True:
        frame = picam2.capture_array()
        img = Image.fromarray(frame, "RGB")

        # Crop to 3:2 (480x320)
        w, h = img.size
        target_ratio = 480 / 320
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

        # Resize for LCD
        img = img.resize((480, 320), Image.BILINEAR)

        # FPS calculation
        frame_count += 1
        now = time.time()
        if now - fps_timer >= 1.0:
            fps = frame_count / (now - fps_timer)
            frame_count = 0
            fps_timer = now

        # Overlay FPS
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, 90, 20), fill=(0, 0, 0))
        draw.text((4, 4), f"{fps:4.1f} FPS", fill=(0, 255, 0))

        # Convert + display
        buf = rgb888_to_rgb565_numpy(img)
        lcd.show_raw_rgb565(buf)

        # Keyboard input
        key = kbd.get_key()
        if key:
            if key.lower() == "q":
                break
            elif key == " ":
                ts = time.strftime("%Y%m%d_%H%M%S")
                fname = save_dir / f"capture_{ts}.jpg"
                img.save(fname, "JPEG", quality=95)
                print(f"Saved {fname}")

except KeyboardInterrupt:
    pass

finally:
    kbd.close()
    picam2.stop()
    lcd.clear((0, 0, 0))
    lcd.close()
