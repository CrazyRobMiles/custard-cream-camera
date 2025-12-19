from ili9486_cpp_style import ILI9486
from PIL import Image

tft = ILI9486()

img = Image.new("RGB", (480,320), (0,0,0))
px = img.load()

for v in range(min(tft._width, tft._height)):
    px[v, v] = (255, 0, 255)

#tft.drawImage(0, 0, img)
tft.drawLandscapeImage(img)