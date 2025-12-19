import time
import spidev
import RPi.GPIO as GPIO

# Commands
MADCTL = 0x36
CASET  = 0x2A
PASET  = 0x2B
RAMWR  = 0x2C
PIXFMT = 0x3A
SLPOUT = 0x11
DISPON = 0x29

# Pins (BCM) – adjust only if yours differ
DC  = 24
RST = 25

SPI_BUS = 0
SPI_DEV = 0
SPI_HZ  = 12_000_000  # keep moderate while locking

def cmd(spi, c):
    GPIO.output(DC, 0)
    spi.writebytes([c])

def data(spi, b):
    GPIO.output(DC, 1)
    if isinstance(b, int):
        spi.writebytes([b])
    else:
        spi.writebytes(list(b))

def data_chunked(spi, buf):
    GPIO.output(DC, 1)
    for i in range(0, len(buf), 4096):
        spi.xfer2(buf[i:i+4096])

def reset():
    GPIO.output(RST, 0)
    time.sleep(0.1)
    GPIO.output(RST, 1)
    time.sleep(0.15)

def init_panel(spi):
    cmd(spi, PIXFMT); data(spi, 0x55)  # RGB565
    cmd(spi, SLPOUT); time.sleep(0.12)
    cmd(spi, DISPON); time.sleep(0.05)

def set_madctl(spi, v):
    cmd(spi, MADCTL)
    data(spi, v)

def set_window(spi, x0, y0, x1, y1):
    cmd(spi, CASET); data(spi, [x0>>8, x0&0xFF, x1>>8, x1&0xFF])
    cmd(spi, PASET); data(spi, [y0>>8, y0&0xFF, y1>>8, y1&0xFF])
    cmd(spi, RAMWR)

def fill(spi, w, h, color565):
    hi = (color565 >> 8) & 0xFF
    lo = color565 & 0xFF
    buf = bytearray([hi, lo]) * (w * h)
    data_chunked(spi, buf)

def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(DC, GPIO.OUT)
    GPIO.setup(RST, GPIO.OUT)

    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEV)
    spi.max_speed_hz = SPI_HZ
    spi.mode = 0

    reset()
    init_panel(spi)

    # ---- YOU WILL EDIT THESE TWO LINES PER STEP ----
    madctl_value = 0xC8
    # Window for LANDSCAPE should be X:0..479, Y:0..319
    set_madctl(spi, madctl_value)
    set_window(spi, 0, 0, 319,479)
    fill(spi, 329, 480, 0x07E0)  # green fill

    time.sleep(1.0)
    # change fill colour to prove overwrite behaviour
    set_window(spi, 0, 0, 479, 319)
    fill(spi, 320,480, 0xF800)  # red fill

    spi.close()
    GPIO.cleanup()

if __name__ == "__main__":
    main()
