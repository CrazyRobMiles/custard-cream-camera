from PIL import Image, ImageDraw, ImageFont
from ii9486_manager import Screen
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


class MagicCamera():
    def __init__(self):
        # Load three font sizes
        self.small_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
        )

        self.medium_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
        )

        self.large_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48
        )
 
        self.picam2 = Picamera2()

        camera_config = self.picam2.create_video_configuration(
            main={"size": (4056, 3040 ), "format": "BGR888"},
            controls={
                "FrameRate": 30
            }
        ) 

        self.picam2.configure(camera_config)
        self.picam2.start()

        self.kbd = Keyboard() 

        self.screen = Screen()

        self.save_dir = Path("captures")
        self.save_dir.mkdir(exist_ok=True)
        
    def save_image(self):
        ts = time.strftime("New_%Y%m%d_%H%M%S")
        fname = self.save_dir / f"capture_{ts}.jpg"
        self.img.save(fname, "JPEG", quality=95)
        print(f"Saved {fname}")
        
    def process_frame(self):

        frame = self.picam2.capture_array()
        self.img = Image.fromarray(frame, "RGB")
        finder = self.img.resize((480, 320))

        draw = ImageDraw.Draw(finder)
        draw.text((10, 10), "Hello World", font=self.small_font, fill="red")
        draw.text((10, 40), "Hello World", font=self.medium_font, fill="green")
        draw.text((10, 90), "Hello World", font=self.large_font, fill="blue")

        self.screen.show_landscape_480x320(finder)
        
    def run(self):
        
        try:
            while True:
                self.process_frame()
                
                key = self.kbd.get_key()
                if key:
                    if key.lower() == "q":
                        return
                    elif key == " ":
                        self.save_image()
    
        except KeyboardInterrupt:
            pass
        finally:   
            self.screen.close()
            self.kbd.close()
            self.picam2.stop()

def main():
    magic_camera = MagicCamera()
    magic_camera.run()

if __name__ == "__main__":
    main()
