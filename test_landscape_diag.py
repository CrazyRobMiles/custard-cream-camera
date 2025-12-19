from PIL import Image
from ili9486_fullscreen import ILI9486FullScreen

tft = ILI9486FullScreen()
tft.clear((0, 0, 0))

img = Image.new("RGB", (480, 320), (0, 0, 0))
px = img.load()

for v in range(min(480, 320)):
    px[v, v] = (255, 0, 255)

tft.show_landscape_480x320(img, rotate=Image.ROTATE_270)
input("Enter to exit...")
tft.close()
