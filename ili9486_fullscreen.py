import time
import spidev
import RPi.GPIO as GPIO
from PIL import Image

ILI9486_MADCTL = 0x36
ILI9486_CASET  = 0x2A
ILI9486_PASET  = 0x2B
ILI9486_RAMWR  = 0x2C
ILI9486_PIXFMT = 0x3A
ILI9486_SLPOUT = 0x11
ILI9486_DISPON = 0x29
import numpy as np


# Fixed working MADCTL for your panel (you confirmed this fills the whole screen)
MADCTL_E8 = 0x88  # MX | MY | MV | BGR

class ILI9486FullScreen:
    # Controller-native portrait framebuffer that maps to your full glass
    FB_W = 320
    FB_H = 480

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
    def _rgb888_to_rgb565_old(img: Image.Image) -> bytearray:
        raw = img.tobytes()
        out = bytearray((len(raw) // 3) * 2)
        i = j = 0
        while i < len(raw):
            r, g, b = raw[i], raw[i+1], raw[i+2]
            val = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[j] = (val >> 8) & 0xFF
            out[j+1] = val & 0xFF
            i += 3
            j += 2
        return out

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
        if img.size != (self.FB_W, self.FB_H):
            img = img.resize((self.FB_W, self.FB_H), Image.BICUBIC)

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
        img = Image.new("RGB", (self.FB_W, self.FB_H), rgb)
        self.show_portrait_320x480(img)

    def close(self):
        self.spi.close()
        GPIO.cleanup()

    def show_raw_rgb565(self, buf: bytes):
        """
        Display a full-screen RGB565 frame.
        Buffer MUST be exactly 320*480*2 bytes.
        """
        if len(buf) != self.FB_W * self.FB_H * 2:
            raise ValueError(
                f"RGB565 buffer wrong size: {len(buf)} "
                f"(expected {self.FB_W * self.FB_H * 2})"
            )

        # Ensure correct mode and window
        self._set_mode_and_full_window()

        # Start memory write
        self._cmd(ILI9486_RAMWR)

        # Stream pixel data
        self._data_chunked(buf)
