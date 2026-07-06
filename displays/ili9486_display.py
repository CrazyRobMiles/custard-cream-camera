import time
import spidev
import RPi.GPIO as GPIO
import numpy as np
from PIL import Image, ImageDraw

from .base import BaseDisplay
from .widgets import ButtonPanel

ILI9486_MADCTL = 0x36
ILI9486_CASET  = 0x2A
ILI9486_PASET  = 0x2B
ILI9486_RAMWR  = 0x2C
ILI9486_PIXFMT = 0x3A
ILI9486_SLPOUT = 0x11
ILI9486_DISPON = 0x29

MADCTL_E8 = 0x88

PENIRQ_PIN = 17


class XPT2046Touch:
    """Raw XPT2046 touch controller, reporting calibrated screen coordinates."""

    MIN_TOUCH_X = 281
    MAX_TOUCH_X = 3859
    MIN_TOUCH_Y = 3724
    MAX_TOUCH_Y = 243

    def __init__(self, on_press, on_release, width, height, bus=0, device=1):
        self.on_press = on_press
        self.on_release = on_release
        self.width = width
        self.height = height
        self.last_x = None
        self.last_y = None

        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 2000000

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PENIRQ_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(
            PENIRQ_PIN,
            GPIO.BOTH,
            callback=self._touch_callback,
            bouncetime=20
        )

    def read_channel(self, command):
        result = self.spi.xfer2([command, 0, 0])
        return ((result[1] << 8) | result[2]) >> 3

    def read(self):
        x = self.read_channel(0xD0)
        y = self.read_channel(0x90)
        return x, y

    def _touch_callback(self, pin):
        if GPIO.input(PENIRQ_PIN):
            # Touch released: use the coordinates recorded on the way down
            if self.last_x is not None and self.last_y is not None:
                self.on_release(self.last_x, self.last_y)
            return

        raw_y = self.read_channel(0xD0)
        raw_x = self.read_channel(0x90)

        x_range = self.MAX_TOUCH_X - self.MIN_TOUCH_X
        x = int(((raw_x - self.MIN_TOUCH_X) / x_range) * self.width)

        y_range = self.MIN_TOUCH_Y - self.MAX_TOUCH_Y
        raw_y = raw_y - self.MAX_TOUCH_Y
        raw_y = y_range - raw_y
        y = int((raw_y / y_range) * self.height)

        self.last_x = x
        self.last_y = y

        self.on_press(x, y)


class ILI9486Display(BaseDisplay):

    HEIGHT = 320
    WIDTH = 480

    def __init__(self, dc_pin=24, reset_pin=25, spi_bus=0, spi_device=0, spi_speed=16_000_000):
        super().__init__()

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

        self.buttons = ButtonPanel()
        self.touch_screen = XPT2046Touch(
            on_press=self.buttons.press,
            on_release=self.buttons.release,
            width=self.WIDTH,
            height=self.HEIGHT,
        )

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
        """Display a 320x480 portrait image that fills the entire glass (confirmed working mapping)."""
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.size != (self.HEIGHT, self.WIDTH):
            img = img.resize((self.HEIGHT, self.WIDTH), Image.BICUBIC)

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
        if img.size != (self.WIDTH, self.HEIGHT):
            img = img.resize((self.WIDTH, self.HEIGHT), Image.BICUBIC)

        # Rotate into the 320x480 portrait framebuffer
        imgp = img.transpose(rotate)  # becomes 320x480
        self.show_portrait_320x480(imgp)

    def clear(self, rgb=(0, 0, 0)):
        img = Image.new("RGB", (self.HEIGHT, self.WIDTH), rgb)
        self.show_portrait_320x480(img)

    def show_raw_rgb565(self, buf: bytes):
        """
        Display a full-screen RGB565 frame.
        Buffer MUST be exactly 320*480*2 bytes.
        """
        if len(buf) != self.HEIGHT * self.WIDTH * 2:
            raise ValueError(
                f"RGB565 buffer wrong size: {len(buf)} "
                f"(expected {self.HEIGHT * self.WIDTH * 2})"
            )

        # Ensure correct mode and window
        self._set_mode_and_full_window()

        # Start memory write
        self._cmd(ILI9486_RAMWR)

        # Stream pixel data
        self._data_chunked(buf)

    # ---------- BaseDisplay interface ----------

    def set_buttons(self, buttons):
        self.buttons.set_buttons(buttons)

    def update(self):
        return self.buttons.update()

    def draw(self, img):
        draw = ImageDraw.Draw(img)
        self.buttons.draw(draw)
        self.show_landscape_480x320(img)

    def close(self):
        self.spi.close()
        GPIO.cleanup()
