#!/usr/bin/env python3
"""Simple Raspberry Pi HQ Camera viewer using Picamera2 and OpenCV.

Run: python3 main.py
Press 'q' in the window to quit.
"""
import sys
import argparse

try:
    from picamera2 import Picamera2
except Exception as e:
    print("Error: could not import picamera2. Install python3-picamera2 or see README.", file=sys.stderr)
    raise

import cv2
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Pi HQ Camera viewer (Picamera2 + OpenCV)")
    p.add_argument("--width", type=int, default=1280, help="preview width")
    p.add_argument("--height", type=int, default=720, help="preview height")
    p.add_argument("--flip", choices=["none", "h", "v", "hv"], default="none", help="flip/hflip/vflip/hvflip")
    return p.parse_args()


def main():
    args = parse_args()

    picam2 = Picamera2()
    try:
        cfg = picam2.create_preview_configuration({"size": (args.width, args.height)})
    except TypeError:
        cfg = picam2.create_preview_configuration(main={"size": (args.width, args.height)})

    picam2.configure(cfg)
    picam2.start()

    window = "HQ Camera"
    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)

    try:
        while True:
            frame = picam2.capture_array()
            # Picamera2 returns RGB by default; convert to BGR for OpenCV
            try:
                bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            except Exception:
                bgr = frame

            if args.flip != "none":
                if "h" in args.flip:
                    bgr = cv2.flip(bgr, 1)
                if "v" in args.flip:
                    bgr = cv2.flip(bgr, 0)

            cv2.imshow(window, bgr)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        pass
    finally:
        picam2.stop()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
