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


class ILI9486:
    # Physical panel size
    TFT_WIDTH  = 480
    TFT_HEIGHT = 320

    def __init__(self,
                 dc_pin=24,        # physical pin 18
                 reset_pin=25,     # physical pin 22
                 spi_bus=0,
                 spi_device=0,
                 spi_speed=8_000_000):

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

        self._rotation = 3  # match your working case
        self._width = None
        self._height = None

        self._reset()
        self._init_display()
        self.setRotation(self._rotation)

    # ------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # Display init
    # ------------------------------------------------------------

    def _init_display(self):
        # Pixel format RGB565
        self._cmd(ILI9486_PIXFMT)
        self._data(0x55)

        self._cmd(ILI9486_SLPOUT)
        time.sleep(0.12)

        self._cmd(ILI9486_DISPON)
        time.sleep(0.05)

    # ------------------------------------------------------------
    # Rotation (DIRECT PORT of your C++)
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # Address window (ILI9486 semantics)
    # ------------------------------------------------------------

    def _setAddrWindow(self, x, y, w, h):
        self._cmd(ILI9486_CASET)
        self._data([x >> 8, x & 0xFF,
                    (x + w - 1) >> 8, (x + w - 1) & 0xFF])

        self._cmd(ILI9486_PASET)
        self._data([y >> 8, y & 0xFF,
                    (y + h - 1) >> 8, (y + h - 1) & 0xFF])

        self._cmd(ILI9486_RAMWR)

    # ------------------------------------------------------------
    # Bitmap draw (DIRECT PORT of startBitmap)
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # RGB conversion
    # ------------------------------------------------------------

    def _rgb_to_565(self, img):
        raw = img.tobytes()
        out = bytearray((len(raw) // 3) * 2)

        i = j = 0
        while i < len(raw):
            r, g, b = raw[i], raw[i+1], raw[i+2]
            val = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[j]   = (val >> 8) & 0xFF
            out[j+1] = val & 0xFF
            i += 3
            j += 2

        return out

    # ------------------------------------------------------------
    # Public draw API
    # ------------------------------------------------------------

    def drawImage(self, x, y, img: Image.Image):
        img = img.convert("RGB")
        w, h = img.size

        self.startBitmap(x, y, w, h)
        buf = self._rgb_to_565(img)
        self._data_chunked(buf)

    def clear(self, color=(0, 0, 0)):
        img = Image.new("RGB", (self._width, self._height), color)
        self.drawImage(0, 0, img)

    # ------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------

    def close(self):
        self.spi.close()
        GPIO.cleanup()

    def drawLandscapeImage(self, img_480x320):
        """
        Draw a full-screen 480x320 LANDSCAPE image.
        """
        assert img_480x320.size == (480, 320), img_480x320.size

        # Rotate landscape → portrait (clockwise)
        img_portrait = img_480x320.transpose(Image.ROTATE_90)


        # Now this is 320x480 and matches the driver perfectly
        self.drawImage(0, 0, img_portrait)
