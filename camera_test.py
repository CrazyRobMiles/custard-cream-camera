from PIL import Image, ImageDraw, ImageFont
from ili9486_fullscreen import ILI9486FullScreen
import termios
import sys
import select
import time
import tty
import numpy as np
from picamera2 import Picamera2
from pathlib import Path
 

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


# Create image
width = 480
height = 320
image = Image.new("RGB", (width, height), "black")
draw = ImageDraw.Draw(image)

# Load three font sizes
small_font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
)

medium_font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
)

large_font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48
)
 
# Draw text
# Save or display


picam2 = Picamera2()

camera_config = picam2.create_video_configuration(
    main={"size": (4056, 3040 ), "format": "BGR888"},
    controls={
        "FrameRate": 30
    }
)

picam2.configure(camera_config)
picam2.start()

kbd = Keyboard()

tft = ILI9486FullScreen()

tft.test_touch_screen()

save_dir = Path("captures")
save_dir.mkdir(exist_ok=True)

try:
    while True:
        frame = picam2.capture_array()
        img = Image.fromarray(frame, "RGB")

        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Hello World", font=small_font, fill="red")
        draw.text((10, 40), "Hello World", font=medium_font, fill="green")
        draw.text((10, 90), "Hello World", font=large_font, fill="blue")

        tft.show_landscape_480x320(img)
        
        # Keyboard input
        key = kbd.get_key()
        if key:
            if key.lower() == "q":
                break
            elif key == " ":
                ts = time.strftime("New_%Y%m%d_%H%M%S")
                fname = save_dir / f"capture_{ts}.jpg"
                img.save(fname, "JPEG", quality=95)
                print(f"Saved {fname}")
    
except KeyboardInterrupt:
    pass

finally:   
    tft.close()
    kbd.close()
    picam2.stop()
