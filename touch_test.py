import spidev
import RPi.GPIO as GPIO
import time

class XPT2046:

    def __init__(self, bus=0, device=1):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 1000000
        self.spi.mode = 0
        
    def read_channel(self, command):
        result = self.spi.xfer2([command, 0, 0])

        value = ((result[1] << 8) | result[2]) >> 3
        return value

    def read(self):
        x = self.read_channel(0xD0)
        y = self.read_channel(0x90)
        return x, y
    

touch = XPT2046()

oldx=-1
oldy=-1

while True:
    x, y = touch.read()
    if x != oldx or y != oldy:
        print(x, y)
    oldx = x
    oldy = y