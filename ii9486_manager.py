import time
import spidev
import RPi.GPIO as GPIO
from PIL import Image
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ILI9486_MADCTL = 0x36
ILI9486_CASET  = 0x2A
ILI9486_PASET  = 0x2B
ILI9486_RAMWR  = 0x2C
ILI9486_PIXFMT = 0x3A
ILI9486_SLPOUT = 0x11
ILI9486_DISPON = 0x29

MADCTL_E8 = 0x88 

PENIRQ_PIN = 17


class Button:

    button_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
    )

    def __init__(self, x, y, width,height,text,text_colour,back_colour,up_handler,down_handler):
        self.x = x
        self.y = y
        self.height = height
        self.width = width
        self.text = text
        self.text_colour = text_colour
        self.back_colour = back_colour
        self.up_handler = up_handler
        self.down_handler = down_handler
        self.pressed = False
        self.enabled = False
        
    def draw(self, draw):
        
        if not self.enabled:
            return
        
        text_colour = self.back_colour if self.pressed else self.text_colur
        back_colour = self.text_colour if self.pressed else self.back_colour
        draw.rectangle((self.x, self.y, 90, 20), fill=back_colour)
        
        bbox = draw.textbbox((0, 0), self.text, font=self.button_font)

        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        text_x = self.x + (self.width - text_w) // 2
        text_y = self.y + (self.height - text_h) // 2
        
        draw.text((text_x, text_y), self.text, font=self.font, fill=text_colour)
        
    def enable(self):
        self.enabled = True
        
    def disable(self):
        self.enabled = False
        
    def check_coord(self,x,y):
        
        if not self.enabled:
            return False
        
        if x<self.x: return False
        if y<self.y: return False
        if x>(self.x+self.width): return False
        if y>(self.y+self.height): return False
        
        return True
        
    def up(self):
        
        if not self.enabled:
            return
        
        print(f"Button: {self.text} released")
        if self.up_handler:
            self.up_handler()
    
    def down(self):
        if not self.enabled:
            return

        print(f"Button: {self.text} pressed")
        if self.down_handler:
            self.down_handler()
            
class Menu:
    
    def touch_callback(self,pin):
        
        if GPIO.input(PENIRQ_PIN):
            print("Touch up")
        else:
            print("Touch down")

        x = self.touch_screen.read_channel(0xD0)
        y = self.touch_screen.read_channel(0x90)
        
        print(f"Button callback x:{x} y:{y}")
        for button in self.buttons:
            if button.check_coord(x,y):
                if GPIO.input(PENIRQ_PIN):
                    button.up()
                else:
                    button.down()

    def __init__(self, touch_screen):
        self.touch_screen = touch_screen
        self.buttons = []
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PENIRQ_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)        
        GPIO.add_event_detect(
            PENIRQ_PIN,
            GPIO.BOTH,
            callback=self.touch_callback,
            bouncetime=20
        )        

    def draw(self,draw):
        for button in self.buttons:
            button.draw(draw)
            
    def set_buttons(self,buttons):
        for button in self.buttons:
            button.disable()
        self.buttons = buttons
        for button in self.buttons:
            button.enable()
        
class XPT2046:

    def __init__(self, bus=0, device=1):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 2000000
        
    def read_channel(self, command):
        result = self.spi.xfer2([command, 0, 0])

        value = ((result[1] << 8) | result[2]) >> 3
        return value

    def read(self):
        x = self.read_channel(0xD0)
        y = self.read_channel(0x90)
        return x, y

class Screen:
    
    DISPLAY_HEIGHT = 320
    DISPLAY_WIDTH = 480

    def __init__(self, dc_pin=24, reset_pin=25, spi_bus=0, spi_device=0, spi_speed=16_000_000):
        self.dc = dc_pin
        self.rst = reset_pin

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.dc, GPIO.OUT)
        GPIO.setup(self.rst, GPIO.OUT)

        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = spi_speed
        self.spi.mode = 0

        self._reset()
        self._init_display()
        self._set_mode_and_full_window()
        
        self.touch_screen = XPT2046()
        self.menu = Menu(self.touch_screen)
        
    def test_touch_screen(self):
        while True:
            x, y = self.touch_screen.read()
            print(x, y)
            
    def get_touch_pos(self):
        return self.touch_screen.read()

    def _reset(self):
        GPIO.output(self.rst, 0)
        time.sleep(0.1)
        GPIO.output(self.rst, 1)
        time.sleep(0.15)

    def _cmd(self, c):
        GPIO.output(self.dc, 0)
        self.spi.writebytes([c])

    def _data(self, data):
        GPIO.output(self.dc, 1)
        if isinstance(data, int):
            self.spi.writebytes([data])
        else:
            self.spi.writebytes(list(data))

    def _data_chunked(self, buf):
        GPIO.output(self.dc, 1)
        for i in range(0, len(buf), 4096):
            self.spi.xfer2(buf[i:i+4096])

    def _init_display(self):
        # Pixel format RGB565
        self._cmd(ILI9486_PIXFMT)
        self._data(0x55)

        self._cmd(ILI9486_SLPOUT)
        time.sleep(0.12)

        self._cmd(ILI9486_DISPON)
        time.sleep(0.05)

    def _set_mode_and_full_window(self):
        # Lock the one known-good mapping
        self._cmd(ILI9486_MADCTL)
        self._data(MADCTL_E8)

        # Full portrait window: 0..319, 0..479
        self._cmd(ILI9486_CASET)
        self._data([0x00, 0x00, 0x01, 0x3F])  # 0..319
        self._cmd(ILI9486_PASET)
        self._data([0x00, 0x00, 0x01, 0xDF])  # 0..479

    def _start_ram_write(self):
        self._cmd(ILI9486_RAMWR)

    @staticmethod
    def _rgb888_to_rgb565(img: Image.Image) -> bytes:
        arr = np.asarray(img, dtype=np.uint8)

        r = (arr[:, :, 0] >> 3).astype(np.uint16)
        g = (arr[:, :, 1] >> 2).astype(np.uint16)
        b = (arr[:, :, 2] >> 3).astype(np.uint16)

        rgb565 = (r << 11) | (g << 5) | b
        return rgb565.byteswap().tobytes()  # big-endian


    # ---------- Public API ----------

    def show_portrait_320x480(self, img: Image.Image):
        """Display a 320x480 portrait image that fills the entire glass (your confirmed working mapping)."""
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.size != (self.DISPLAY_HEIGHT, self.DISPLAY_WIDTH):
            img = img.resize((self.DISPLAY_HEIGHT, self.DISPLAY_WIDTH), Image.BICUBIC)

        self._set_mode_and_full_window()
        self._start_ram_write()
        buf = self._rgb888_to_rgb565(img)
        self._data_chunked(buf)

    def show_landscape_480x320(self, img: Image.Image, rotate=Image.ROTATE_270):
        """
        Display a full-screen 480x320 landscape image.

        rotate determines which way landscape is mapped into the portrait framebuffer.
        Start with ROTATE_270; if mirrored, try ROTATE_90 (but do not change anything else).
        """
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.size != (480, 320):
            img = img.resize((480, 320), Image.BICUBIC)

        # Rotate into the 320x480 portrait framebuffer

        imgp = img.transpose(rotate)  # becomes 320x480
        self.show_portrait_320x480(imgp)

    def clear(self, rgb=(0, 0, 0)):
        img = Image.new("RGB", (self.DISPLAY_HEIGHT, self.DISPLAY_WIDTH), rgb)
        self.show_portrait_320x480(img)

    def close(self):
        self.spi.close()
        GPIO.cleanup()

    def show_raw_rgb565(self, buf: bytes):
        """
        Display a full-screen RGB565 frame.
        Buffer MUST be exactly 320*480*2 bytes.
        """
        if len(buf) != self.DISPLAY_HEIGHT * self.DISPLAY_WIDTH * 2:
            raise ValueError(
                f"RGB565 buffer wrong size: {len(buf)} "
                f"(expected {self.DISPLAY_HEIGHT * self.DISPLAY_WIDTH * 2})"
            )

        # Ensure correct mode and window
        self._set_mode_and_full_window()

        # Start memory write
        self._cmd(ILI9486_RAMWR)

        # Stream pixel data
        self._data_chunked(buf)
