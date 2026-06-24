from PIL import Image, ImageDraw, ImageFont
from ii9486_manager import Screen,Menu,Button
import termios
import sys
import select
import time
import tty
import numpy as np
from picamera2 import Picamera2
from pathlib import Path
from threading import Event
 
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
            main={"size": (400, 320 ), "format": "BGR888"},
            controls={
                "FrameRate": 30
            }
        ) 

        self.preview_config = self.picam2.create_preview_configuration(
            main={"size": (480, 320), "format": "BGR888"}
        )

        self.still_config = self.picam2.create_still_configuration(
            main={"size": (4056, 3040), "format": "BGR888"}
        )

        self.picam2.configure(self.preview_config)
        self.picam2.start()

        self.frame_ready = Event()
        
        self.request_next_frame()
        
        self.kbd = Keyboard() 

        self.screen = Screen()

        main_menu = (
            Button(0,0,200,50,"Click",self.medium_font,(255,255,255),(0,0,0),None,self.save_image),
            Button(210,0,200,50,"Stop",self.medium_font,(255,0,255),(0,0,255),None,self.stop_running)
        )
        
        self.screen.menu.set_buttons(main_menu)

        self.save_dir = Path("captures")
        self.save_dir.mkdir(exist_ok=True)
        
        self.finder=None
        self.img = None
        self.running = None
        
    def stop_running(self):
        self.running = False
        
    def save_image(self):
        ts = time.strftime("New_%Y%m%d_%H%M%S")
        fname = self.save_dir / f"capture_{ts}.jpg"
        self.picam2.switch_mode_and_capture_file(self.still_config, str(fname))
        print(f"Saved {fname}")
        
    def request_next_frame(self):
        self.pending_job = self.picam2.capture_request(
            wait=False,
            signal_function=lambda job: self.frame_ready.set()
        )

    def process_frame(self):
        
        dirty = False

        if self.frame_ready.is_set():
            self.frame_ready.clear()
            request = self.picam2.wait(self.pending_job)
            frame = request.make_array("main")
            request.release()
            
            self.finder = Image.fromarray(frame, "RGB")

            dirty = True
            
            self.request_next_frame()
            
        if self.screen.update():
            dirty=True

        if dirty:
            if self.finder != None:
                self.screen.draw(self.finder)
        
    def run(self):
        self.running = True
        try:
            while self.running:

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
