from PIL import Image,ImageDraw
from ili9486_fullscreen import ILI9486FullScreen


import spidev
import spidev
import RPi.GPIO as GPIO

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

touch = XPT2046()

while True:
    x, y = touch.read()
    print(x, y)


tft = ILI9486FullScreen()
tft.clear((0, 0, 0))

img = Image.new("RGB", (480, 320), (0, 0, 0))
px = img.load()

for y in range(320):
    for x in range(480):
        px[x, y] = (255, 0, 0)

draw = ImageDraw.Draw(img)
draw.rectangle((0, 0, 90, 20), fill=(0, 0, 0))
fps=99
draw.text((4, 4), f"HELLO WORLD", fill=(255, 255, 255))

tft.show_landscape_480x320(img, rotate=Image.ROTATE_270)
input("Enter to exit...")
tft.close()
