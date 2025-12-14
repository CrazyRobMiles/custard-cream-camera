# Nanobanana Camera

A homage to the one made by [Nikbuild](https://github.com/nickbild/banamera)

This repository provides a small Python app that captures video from the
Raspberry Pi HQ Camera using `picamera2` and displays it in a desktop window
using OpenCV.

Quick start

- Enable the camera stack (libcamera) in `raspi-config` if needed.
- Install system packages and Python dependencies (example for Raspberry Pi OS):

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-numpy
```

Alternatively install Python packages via pip (some packages are better
installed from apt on Raspberry Pi):

```bash
python3 -m pip install -r requirements.txt
```

- Run the app:

```bash
python3 main.py
```

Press `q` in the window to quit.

Notes

- This program uses `picamera2` (libcamera backend). It requires a configured
	camera and the desktop environment to display the OpenCV window.
- If you're on a headless Pi, you can run this with a virtual display (Xvfb)
	or adapt the code to stream frames elsewhere.