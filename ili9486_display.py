import time
import spidev
import RPi.GPIO as GPIO
from PIL import Image

# ILI9486 commands
ILI9486_MADCTL = 0x36
ILI9486_RAMWR  = 0x2C
ILI9486_CASET  = 0x2A
ILI9486_PASET  = 0x2B
ILI9486_PIXFMT = 0x3A
ILI9486_SLPOUT = 0x11
ILI9486_DISPON = 0x29


# MADCTL bits
MADCTL_MY  = 0x80
MADCTL_MX  = 0x40
MADCTL_MV  = 0x20
MADCTL_ML  = 0x10
MADCTL_BGR = 0x08
MADCTL_MH  = 0x04

class ILI9486Display:

    TFT_WIDTH  = 480
    TFT_HEIGHT = 320

    def __init__(
        self,
        dc_pin=24,        # physical pin 18
        reset_pin=25,     # physical pin 22
        spi_bus=0,
        spi_device=0,     # CE0
        spi_speed=8_000_000,
    ):
        self.dc = dc_pin
        self.rst = reset_pin

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.dc, GPIO.OUT)
        GPIO.setup(self.rst, GPIO.OUT)

        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = spi_speed
        self.spi.mode = 0

        self._rotation = 3  # match your working case
        self._width = None
        self._height = None

        self._reset()
        self._init_display()
        self.setRotation(self._rotation)

    # -------------------------------------------------

    def setRotation(self, m):
        self._rotation = m % 4

        self._cmd(ILI9486_MADCTL)

        if self._rotation == 0:
            self._data(MADCTL_MX | MADCTL_BGR)
            self._width  = self.TFT_WIDTH
            self._height = self.TFT_HEIGHT

        elif self._rotation == 1:
            self._data(MADCTL_MV | MADCTL_BGR)
            self._width  = self.TFT_HEIGHT
            self._height = self.TFT_WIDTH

        elif self._rotation == 2:
            self._data(MADCTL_MY | MADCTL_BGR)
            self._width  = self.TFT_WIDTH
            self._height = self.TFT_HEIGHT

        elif self._rotation == 3:
            self._data(MADCTL_MX | MADCTL_MY | MADCTL_MV | MADCTL_BGR)
            self._width  = self.TFT_HEIGHT
            self._height = self.TFT_WIDTH

    def _reset(self):
        GPIO.output(self.rst, 0)
        time.sleep(0.1)
        GPIO.output(self.rst, 1)
        time.sleep(0.15)

    def _cmd(self, c):
        GPIO.output(self.dc, 0)
        self.spi.writebytes([c])

    def _data(self, d):
        GPIO.output(self.dc, 1)
        if isinstance(d, int):
            self.spi.writebytes([d])
        else:
            self.spi.writebytes(list(d))

    # -------------------------------------------------

    def _init_display(self):
        # Power / control
        self._cmd(0xF1)
        self._data([0x36, 0x04, 0x00, 0x3C, 0x0F, 0x8F])

        self._cmd(0xF2)
        self._data([0x18, 0xA3, 0x12, 0x02, 0xB2, 0x12, 0xFF, 0x10, 0x00])

        self._cmd(0xF8)
        self._data([0x21, 0x04])

        self._cmd(0xF9)
        self._data([0x00, 0x08])

        # Interface mode
        self._cmd(0xB0)
        self._data(0x00)

        # RGB565
        self._cmd(0x3A)
        self._data(0x55)

        self._cmd(0x11)  # sleep out
        time.sleep(0.12)

        self._cmd(0x29)  # display on
        time.sleep(0.05)

    # -------------------------------------------------

    def _setAddrWindow(self, x, y, w, h):
        self._cmd(ILI9486_CASET)
        self._data([x >> 8, x & 0xFF,
                    (x + w - 1) >> 8, (x + w - 1) & 0xFF])

        self._cmd(ILI9486_PASET)
        self._data([y >> 8, y & 0xFF,
                    (y + h - 1) >> 8, (y + h - 1) & 0xFF])

        self._cmd(ILI9486_RAMWR)

    # -------------------------------------------------

    def startBitmap(self, x, y, w, h):
        self._cmd(ILI9486_MADCTL)

        if self._rotation == 0:
            self._data(MADCTL_MX | MADCTL_MY | MADCTL_ML | MADCTL_BGR)
        elif self._rotation == 1:
            self._data(MADCTL_MH | MADCTL_MV | MADCTL_MX | MADCTL_BGR)
        elif self._rotation == 2:
            self._data(MADCTL_MH | MADCTL_BGR)
        elif self._rotation == 3:
            self._data(MADCTL_MV | MADCTL_MY | MADCTL_BGR)

        # **THIS IS THE IMPORTANT Y-FLIP**
        cy = self._height - y - h
        self._setAddrWindow(x, cy, w, h)

    def _blit_rgb565(self, buf):
        GPIO.output(self.dc, 1)
        for i in range(0, len(buf), 4096):
            self.spi.xfer2(buf[i:i+4096])

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------

    def clear(self, color=(0, 0, 0)):
        img = Image.new("RGB", (self._width, self._height), color)
        self._display_image(img)

    def test_pattern(self):
        img = Image.new("RGB", (self._width, self._height), (0, 0, 0))
        px = img.load()

        for v in range(32):
            px[v, v] = (255, 0, 255)


        # for x in range(self._width):
        #     px[x, 0] = (255, 255, 255)
        #     px[x, self._height-1] = (255, 255, 255)
        # for y in range(self._height):
        #     px[0, y] = (255, 255, 255)
        #     px[self._width-1, y] = (255, 255, 255)

        # for y in range(self._height):
        #     for x in range(0, 20):
        #         px[x, y] = (255, 0, 0)
        #     for x in range(self._width-20, self._width):
        #         px[x, y] = (0, 0, 255)

        self._display_image(0,0,img)

    def display_image(self, path):
        img = Image.open(path).convert("RGB")
        #img = img.resize((self._width, self._height), Image.BICUBIC)
        self._display_image(0,0,img)

    def _pil_to_rgb565(self, img):
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

    def crazy_test(self):


        for y in range(self._height):
            for x in range(self._width):
                img = Image.new("RGB", (self._width, self._height), (0, 0, 0))
                px = img.load()
                px[x,y]=(255,0,255)
                self._display_image(0,0,img)

    def _display_image(self,x,y, img):
        img = img.convert("RGB")
        w, h = img.size
        self.startBitmap(x, y, w, h)
        buf = self._pil_to_rgb565(img)
        self._blit_rgb565(buf)

    def close(self):
        self.spi.close()
        GPIO.cleanup()


