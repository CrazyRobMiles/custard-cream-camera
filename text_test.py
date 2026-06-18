from PIL import Image, ImageDraw, ImageFont
from ili9486_fullscreen import ILI9486FullScreen

# Create image
width = 480
height = 320
image = Image.new("RGB", (width, height), "grey")
draw = ImageDraw.Draw(image)

# Load three font sizes
small_font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
)

medium_font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
)

large_font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48
)

# Draw text
draw.text((10, 10), "Hello World", font=small_font, fill="white")
draw.text((10, 40), "Hello World", font=medium_font, fill="yellow")
draw.text((10, 90), "Hello World", font=large_font, fill="cyan")

# Save or display

tft = ILI9486FullScreen()

tft.show_landscape_480x320(image)
tft.close()

