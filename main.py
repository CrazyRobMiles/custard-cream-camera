#!/usr/bin/env python3
"""Simple Raspberry Pi HQ Camera viewer with optional voice-command image processing.

Run: python3 main.py --voice
Press 'q' in the window to quit.
"""
import sys
import argparse
import tempfile
import time
import os

try:
    from picamera2 import Picamera2
except Exception:
    print("Error: could not import picamera2. Install python3-picamera2 or see README.", file=sys.stderr)
    raise

import cv2
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Pi HQ Camera viewer (Picamera2 + OpenCV) with voice commands")
    p.add_argument("--width", type=int, default=320, help="preview width")
    p.add_argument("--height", type=int, default=240, help="preview height")
    p.add_argument("--flip", choices=["none", "h", "v", "hv"], default="none", help="flip/hflip/vflip/hvflip")
    p.add_argument("--voice", action="store_true", help="capture one frame and apply voice commands from microphone")
    p.add_argument("--record-secs", type=float, default=4.0, help="seconds to record voice for commands")
    return p.parse_args()


def record_audio(wav_path, duration=4.0, samplerate=16000, channels=1):
    try:
        import sounddevice as sd
        import soundfile as sf
    except Exception as e:
        raise RuntimeError("sounddevice/soundfile required for recording: install sounddevice and soundfile") from e

    print(f"Recording {duration}s of audio to {wav_path}...")
    data = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=channels, dtype='int16')
    sd.wait()
    sf.write(wav_path, data, samplerate)
    print("Recording complete")


def transcribe_audio(wav_path):
    # Prefer Google GenAI if configured, then try Whisper (local), then SpeechRecognition
    try:
        api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GOOGLE_GENAI_API_KEY')
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                print("Transcribing with Google GenAI...")
                with open(wav_path, 'rb') as af:
                    # Attempt common GenAI audio transcribe surface; exact API may vary by SDK version
                    try:
                        resp = genai.audio.transcribe(model='gpt-4o-mini-transcribe', file=af)
                        text = getattr(resp, 'text', None) or resp.get('text', '') or resp.get('transcript', '')
                    except Exception:
                        # alternate method
                        resp = genai.audio.transcribe(file=af)
                        text = getattr(resp, 'text', None) or resp.get('text', '') or resp.get('transcript', '')
                text = (text or '').strip()
                print("Google GenAI transcription:", text)
                if text:
                    return text
            except Exception as e:
                print("google.generativeai transcription failed:", e)
    except Exception:
        pass

    try:
        import whisper
        print("Transcribing with Whisper (local)...")
        model = whisper.load_model("tiny")
        res = model.transcribe(wav_path)
        text = res.get("text", "").strip()
        print("Whisper transcription:", text)
        return text
    except Exception:
        pass

    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
        print("Transcribing with Google Speech Recognition (online)...")
        text = r.recognize_google(audio)
        print("Google transcription:", text)
        return text
    except Exception as e:
        print("Transcription failed:", e)
        return ""


def parse_commands(text):
    if not text:
        return []
    text = text.lower()
    # split by ' and ' or commas
    parts = [p.strip() for p in text.replace(',', ' and ').split(' and ') if p.strip()]
    return parts


def apply_commands(image, commands):
    img = image.copy()
    saved_path = None
    for cmd in commands:
        print("Applying command:", cmd)
        if 'grayscale' in cmd or 'gray' in cmd:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif 'invert' in cmd or 'negative' in cmd:
            img = cv2.bitwise_not(img)
        elif 'blur' in cmd:
            import re
            m = re.search(r'blur\s*(\d+)', cmd)
            k = int(m.group(1)) if m else 5
            k = k if k % 2 == 1 else k + 1
            img = cv2.GaussianBlur(img, (k, k), 0)
        elif 'canny' in cmd or 'edges' in cmd:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            img = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        elif 'rotate' in cmd:
            import re
            m = re.search(r'rotate\s*(\-?\d+)', cmd)
            ang = int(m.group(1)) if m else 90
            h, w = img.shape[:2]
            M = cv2.getRotationMatrix2D((w/2, h/2), ang, 1)
            img = cv2.warpAffine(img, M, (w, h))
        elif 'flip' in cmd:
            if 'horizontal' in cmd or 'h' == cmd.strip():
                img = cv2.flip(img, 1)
            elif 'vertical' in cmd or 'v' == cmd.strip():
                img = cv2.flip(img, 0)
        elif 'brightness' in cmd or 'brighten' in cmd or 'darker' in cmd:
            import re
            m = re.search(r'(-?\d+)', cmd)
            val = int(m.group(1)) if m else 30
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            h, s, v = cv2.split(hsv)
            v = cv2.add(v, val)
            final_hsv = cv2.merge((h, s, v))
            img = cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR)
        elif 'resize' in cmd:
            import re
            m = re.search(r'(\d+)x(\d+)', cmd)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                img = cv2.resize(img, (w, h))
        elif cmd.startswith('save') or cmd.startswith('store'):
            parts = cmd.split()
            if len(parts) >= 2:
                saved_path = parts[1]
                cv2.imwrite(saved_path, img)
                print(f"Saved processed image to {saved_path}")
        else:
            print("Unknown command:", cmd)

    return img, saved_path


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
        if args.voice:
            # capture a single frame
            frame = picam2.capture_array()
            try:
                bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            except Exception:
                bgr = frame

            if args.flip != "none":
                if "h" in args.flip:
                    bgr = cv2.flip(bgr, 1)
                if "v" in args.flip:
                    bgr = cv2.flip(bgr, 0)

            # record audio
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tf:
                wav_path = tf.name
            try:
                record_audio(wav_path, duration=args.record_secs)
                text = transcribe_audio(wav_path)
            finally:
                try:
                    os.unlink(wav_path)
                except Exception:
                    pass

            cmds = parse_commands(text)
            if not cmds:
                print("No commands recognized from speech.")
            processed, saved = apply_commands(bgr, cmds)

            # display original and processed side-by-side
            combined = np.hstack([bgr, processed])
            cv2.imshow(window, combined)
            print('Transcription:', text)
            print('Commands:', cmds)
            print("Press any key in the window to exit")
            cv2.waitKey(0)
        else:
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
