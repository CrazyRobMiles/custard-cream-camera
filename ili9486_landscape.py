import time
import spidev
import RPi.GPIO as GPIO

# ILI9486 commands
ILI9486_MADCTL = 0x36
ILI9486_CASET  = 0x2A
ILI9486_PASET  = 0x2B
ILI9486_RAMWR  = 0x2C
ILI9486_PIXFMT = 0x3A
ILI9486_SLPOUT = 0x11
ILI9486_DISPON = 0x29

# MADCTL bits
MADCTL_MX  = 0x40
MADCTL_MY = 0x80
MADCTL_MV  = 0x20
MADCTL_BGR = 0x08

# Final landscape MADCTL
MADCTL_LANDSCAPE = MADCTL_MV | MADCTL_MX | MADCTL_BGR  # 0x68
#MADCTL_LANDSCAPE = MADCTL_MV | MADCTL_BGR   # remove MX
#MADCTL_LANDSCAPE = MADCTL_MV | MADCTL_MY | MADCTL_BGR

class ILI9486Landscape:
    """
    Landscape-only, full-screen ILI9486 driver.

    Expects RGB565 buffers sized exactly 480x320.
    No rotation, no portrait support, no partial windows.
    """

    WIDTH  = 480
    HEIGHT = 320
    BYTES  = WIDTH * HEIGHT * 2

    def __init__(self,
                 dc_pin=24,        # BCM for pin 18
                 reset_pin=25,     # BCM for pin 22
                 spi_bus=0,
                 spi_device=0,
                 spi_speed=12_000_000):

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
        self._set_landscape_mode()
        self._set_full_window()

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
    # Display setup
    # ------------------------------------------------------------

    def _init_display(self):
        self._cmd(ILI9486_PIXFMT)
        self._data(0x55)  # RGB565

        self._cmd(ILI9486_SLPOUT)
        time.sleep(0.12)

        self._cmd(ILI9486_DISPON)
        time.sleep(0.05)

    def _set_landscape_mode(self):
        self._cmd(ILI9486_MADCTL)
        self._data(MADCTL_LANDSCAPE)

    def _set_full_window(self):
        # X: 0..479
        self._cmd(ILI9486_CASET)
        self._data([0x00, 0x00, 0x01, 0xDF])

        # Y: 0..319
        self._cmd(ILI9486_PASET)
        self._data([0x00, 0x00, 0x01, 0x3F])

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def show_rgb565(self, buf: bytes):
        """
        Display a full-screen RGB565 landscape frame.

        Buffer must be exactly 480x320x2 bytes.
        """
        if len(buf) != self.BYTES:
            raise ValueError(
                f"RGB565 buffer wrong size: {len(buf)} "
                f"(expected {self.BYTES})"
            )

        # Ensure mode/window are correct (idempotent)
        self._set_landscape_mode()
        self._set_full_window()

        self._cmd(ILI9486_RAMWR)
        self._data_chunked(buf)

    def clear(self, color565=0x0000):
        hi = (color565 >> 8) & 0xFF
        lo = color565 & 0xFF
        buf = bytearray([hi, lo]) * (self.WIDTH * self.HEIGHT)
        self.show_rgb565(buf)

    def close(self):
        self.spi.close()
        GPIO.cleanup()
