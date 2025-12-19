import time
import sys
import termios
import tty
import select
from pathlib import Path

import numpy as np
from picamera2 import Picamera2
from PIL import Image, ImageDraw

from ili9486_portrait import ILI9486Portrait


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

def rgb888_to_rgb565_numpy(img):
    arr = np.asarray(img, dtype=np.uint8)
    r = (arr[:, :, 0] >> 3).astype(np.uint16)
    g = (arr[:, :, 1] >> 2).astype(np.uint16)
    b = (arr[:, :, 2] >> 3).astype(np.uint16)
    return ((r << 11) | (g << 5) | b).byteswap().tobytes()

def fit_inside(src_w, src_h, dst_w, dst_h):
    src_ratio = src_w / src_h
    dst_ratio = dst_w / dst_h

    if src_ratio > dst_ratio:
        # limited by width
        w = dst_w
        h = int(dst_w / src_ratio)
    else:
        # limited by height
        h = dst_h
        w = int(dst_h * src_ratio)

    x = (dst_w - w) // 2
    y = (dst_h - h) // 2
    return x, y, w, h

def fit_landscape_into_portrait(src_w, src_h, dst_w=320, dst_h=480):
    # Landscape target inside portrait
    target_ratio = 480 / 320   # landscape aspect (3:2)

    if src_w / src_h > target_ratio:
        # too wide
        w = dst_w
        h = int(dst_w / (src_w / src_h))
    else:
        # too tall
        h = int(dst_h * 320 / 480)
        w = int(h * (src_w / src_h))

    x = (dst_w - w) // 2
    y = (dst_h - h) // 2
    return x, y, w, h


# ------------------------------------------------------------
# Display
# ------------------------------------------------------------

lcd = ILI9486Portrait(spi_speed=12_000_000)
lcd.clear(0x0000)


# ------------------------------------------------------------
# Camera
# ------------------------------------------------------------

picam2 = Picamera2()

preview_config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "RGB888"},
    controls={"FrameRate": 30}
)

still_config = picam2.create_still_configuration()

picam2.configure(preview_config)
picam2.start()
time.sleep(0.5)


# ------------------------------------------------------------
# Runtime state
# ------------------------------------------------------------

kbd = Keyboard()
frame_counter = 0

save_dir = Path("captures")
save_dir.mkdir(exist_ok=True)

print("SPACE = shutter, Q = quit")


# ------------------------------------------------------------
# Main loop
# ------------------------------------------------------------

try:
    while True:
        # Original camera frame (RGB888)
        frame = picam2.capture_array()
        frame_counter += 1

        # Convert to PIL
        src = Image.fromarray(frame, "RGB")

        # ---- Build landscape preview first ----

        # Scale camera frame to landscape preview that fits width
        # (we'll letterbox vertically after rotation)
        preview = src.resize((480, 320), Image.BILINEAR)

        # Rotate preview into portrait orientation
        preview = preview.transpose(Image.ROTATE_90)   # now 320 x 480

        preview = preview.transpose(Image.FLIP_TOP_BOTTOM)

        # ---- Compose into portrait canvas ----

        canvas = Image.new("RGB", (320, 480), (0, 0, 0))

        # Compute centred paste position USING ROTATED SIZE
        pw, ph = preview.size   # should be (320, 480)
        x = (canvas.width  - pw) // 2
        y = (canvas.height - ph) // 2

        canvas.paste(preview, (x, y))

        # Overlay frame counter
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 140, 24), fill=(0, 0, 0))
        draw.text((6, 4), f"Frames: {frame_counter}", fill=(0, 255, 0))

        # Convert and display
        buf = rgb888_to_rgb565_numpy(canvas)
        lcd.show_rgb565(buf)

        # ---- Input ----
        key = kbd.get()
        if key:
            if key.lower() == "q":
                break
            elif key == " ":
                ts = time.strftime("%Y%m%d_%H%M%S")
                fname = save_dir / f"still_{ts}.jpg"

                # Capture to memory
                request = picam2.switch_mode_and_capture_request(still_config)
                frame = request.make_array("main")
                request.release()

                # Rotate 180° for correct orientation
                img = Image.fromarray(frame, "RGB")
                img = img.transpose(Image.ROTATE_180)

                # Save corrected image
                img.save(fname, "JPEG", quality=95)
                print(f"Captured {fname}")

except KeyboardInterrupt:
    pass

finally:
    kbd.close()
    picam2.stop()
    lcd.clear(0x0000)
    lcd.close()
