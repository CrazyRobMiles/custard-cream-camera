import time
import sys
import termios
import tty
import select
from pathlib import Path

import numpy as np
from picamera2 import Picamera2
from PIL import Image, ImageDraw

from ili9486_landscape import ILI9486Landscape


# ------------------------------------------------------------
# Keyboard (non-blocking)
# ------------------------------------------------------------

class Keyboard:
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

    def get(self):
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
    return rgb565.byteswap().tobytes()


# ------------------------------------------------------------
# Display setup (LANDSCAPE ONLY)
# ------------------------------------------------------------

lcd = ILI9486Landscape(
    dc_pin=24,
    reset_pin=25,
    spi_speed=12_000_000
)

lcd.clear(0x0000)


# ------------------------------------------------------------
# Camera setup (HQ Camera)
# ------------------------------------------------------------

picam2 = Picamera2()

camera_config = picam2.create_video_configuration(
    main={
        "size": (640, 480),      # Landscape capture
        "format": "RGB888"
    },
    controls={
        "FrameRate": 30
    }
)

picam2.configure(camera_config)
picam2.start()

time.sleep(0.5)  # warm-up


# ------------------------------------------------------------
# Runtime state
# ------------------------------------------------------------

kbd = Keyboard()

frame_count = 0
fps = 0.0
fps_timer = time.time()

save_dir = Path("captures")
save_dir.mkdir(exist_ok=True)

print("Controls: SPACE = capture, Q = quit")


# ------------------------------------------------------------
# Main loop
# ------------------------------------------------------------

try:
    while True:
        frame = picam2.capture_array()   # NumPy array RGB888
        img = Image.fromarray(frame, "RGB")

        # Crop to 3:2 (480x320) without distortion
        w, h = img.size
        target_ratio = 480 / 320

        if w / h > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
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
        draw.rectangle((0, 0, 100, 22), fill=(0, 0, 0))
        draw.text((6, 4), f"{fps:4.1f} FPS", fill=(0, 255, 0))

        # Convert and display
        buf = rgb888_to_rgb565_numpy(img)
        lcd.show_rgb565(buf)

        # Keyboard handling
        key = kbd.get()
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
    lcd.clear(0x0000)
    lcd.close()
