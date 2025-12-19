import time
from picamera2 import Picamera2
from PIL import Image

from ili9486_fullscreen import ILI9486FullScreen


# -------------------------------
# Display setup
# -------------------------------

lcd = ILI9486FullScreen(
    dc_pin=24,        # BCM for pin 18
    reset_pin=25,     # BCM for pin 22
    spi_speed=8_000_000
)

lcd.clear((0, 0, 0))


# -------------------------------
# Camera setup (HQ camera)
# -------------------------------

picam2 = Picamera2()

# Capture at native landscape aspect ratio
# We deliberately capture bigger than the LCD for decent quality
camera_config = picam2.create_video_configuration(
    main={
        "size": (1280, 720),     # 16:9, good downscale
        "format": "RGB888"
    },
    controls={
        "FrameRate": 30
    }
)

picam2.configure(camera_config)
picam2.start()

time.sleep(0.5)  # camera warm-up


# -------------------------------
# Main loop
# -------------------------------

try:
    while True:
        # Capture frame as numpy array (H, W, 3)
        frame = picam2.capture_array()

        # Convert to Pillow image
        img = Image.fromarray(frame, "RGB")

        # Crop to 3:2 to match 480×320 (avoid distortion)
        w, h = img.size
        target_ratio = 480 / 320

        if w / h > target_ratio:
            # Too wide → crop left/right
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
            # Too tall → crop top/bottom
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))

        # Resize to LCD resolution
        img = img.resize((480, 320), Image.BILINEAR)

        # Display full-screen landscape
        lcd.show_landscape_480x320(img)

except KeyboardInterrupt:
    print("Stopping...")

finally:
    picam2.stop()
    lcd.clear((0, 0, 0))
    lcd.close()
