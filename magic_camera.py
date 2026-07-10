import io
import json
import select
import subprocess
import sys
import tempfile
import termios
import time
import tty
from pathlib import Path
from threading import Event, Thread

from PIL import Image, ImageDraw, ImageFont
from picamera2 import Picamera2

from displays import Button, create_display
from nanobanana import AudioRecorder, NanobananaClient
from shutter_remote import ShutterRemote

SETTINGS_PATH = Path(__file__).parent / "settings.json"


def load_settings():
    with open(SETTINGS_PATH) as f:
        return json.load(f)


# ------------------------------------------------------------
# Keyboard handling (non-blocking)
# ------------------------------------------------------------

class Keyboard:
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

    def get_key(self):
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def close(self):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


class MagicCamera():

    def __init__(self):
        settings = load_settings()

        # Load three font sizes
        self.small_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
        )

        self.medium_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
        )

        self.large_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48
        )

        self.picam2 = Picamera2()

        self.preview_config = self.picam2.create_preview_configuration(
            main={"size": (480, 320), "format": "BGR888"}
        )

        self.still_config = self.picam2.create_still_configuration(
            main={"size": (4056, 3040), "format": "BGR888"}
        )

        self.picam2.configure(self.preview_config)
        self.picam2.start()

        self.frame_ready = Event()

        self.request_next_frame()

        self.kbd = Keyboard()

        self.screen = create_display(settings)

        button_y = self.screen.HEIGHT - 50

        main_menu = (
            Button(0, button_y, 110, 50, "Click", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.save_image),
            Button(123, button_y, 110, 50, "Speak", self.medium_font, (255, 255, 255), (0, 110, 0), self.finish_voice_prompt, self.start_voice_prompt),
            Button(246, button_y, 110, 50, "Print", self.medium_font, (255, 255, 255), (90, 90, 90), None, self.print_image),
            Button(369, button_y, 110, 50, "Stop", self.medium_font, (255, 0, 255), (0, 0, 255), None, self.stop_running),
        )

        self.screen.set_buttons(main_menu)

        self.save_dir = Path("captures")
        self.save_dir.mkdir(exist_ok=True)

        self.printer_name = settings.get("printing", {}).get("printer")

        self.finder = None
        self.img = None
        self.running = None
        self.save_file_name = None
        self.last_photo_path = None

        # Voice-prompted AI edit ("Speak" button)
        nanobanana_settings = settings.get("nanobanana", {})
        self.nanobanana_settings = nanobanana_settings
        self.audio_recorder = AudioRecorder(
            sample_rate=nanobanana_settings.get("sample_rate", 16000),
            channels=nanobanana_settings.get("channels", 1),
            max_seconds=nanobanana_settings.get("max_record_seconds", 15),
            device=nanobanana_settings.get("device"),
        )
        self.audio_path = Path(tempfile.gettempdir()) / "magic_camera_prompt.wav"
        self.nanobanana_client = None
        self.ai_pending = False
        self.ai_done = Event()
        self.ai_result = None

        # Bluetooth shutter remote - the physical button sends a real press+release, so the
        # "speak" key drives hold-to-talk the same way the on-screen Speak button does. All the
        # Events below are set from the remote's background listener thread and only ever acted
        # on in process_frame(), on the main thread, since drawing/Picamera2 calls aren't safe
        # to make from a background thread.
        remote_settings = settings.get("shutter_remote", {})
        self.remote_photo_requested = Event()
        self.remote_speak_down = Event()
        self.remote_speak_up = Event()
        self.shutter_remote = None
        if remote_settings.get("enabled", False):
            bindings = {}
            photo_key = remote_settings.get("photo_key", "KEY_VOLUMEUP")
            speak_key = remote_settings.get("speak_key", "KEY_ENTER")
            if photo_key:
                bindings[photo_key] = (self.remote_photo_requested.set, None)
            if speak_key:
                bindings[speak_key] = (self.remote_speak_down.set, self.remote_speak_up.set)

            self.shutter_remote = ShutterRemote(
                bindings=bindings,
                device_name=remote_settings.get("device_name"),
                grab=remote_settings.get("grab", False),
            )
            self.shutter_remote.start()

    def stop_running(self):
        print("Doing Stop action")
        self.running = False

    def save_image(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.save_file_name = self.save_dir / f"capture_{ts}.jpg"
        self.picam2.switch_mode_and_capture_file(self.still_config, str(self.save_file_name))
        self.last_photo_path = self.save_file_name
        print(f"Saved {self.save_file_name}")

    def print_image(self):
        if self.last_photo_path is None:
            print("Nothing to print yet")
            self.show_result(self.status_frame("Nothing to print yet"), hold_seconds=2)
            return

        print(f"Printing {self.last_photo_path}")
        self.show_result(self.status_frame("Printing..."), hold_seconds=1)

        cmd = ["lp"]
        if self.printer_name:
            cmd += ["-d", self.printer_name]
        cmd.append(str(self.last_photo_path))

        try:
            # `lp` just queues the job with CUPS and returns immediately - it doesn't wait
            # for the physical print to finish - so this stays quick regardless of printer speed.
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Print failed: {e}")
            if self.printer_name is None:
                print("No 'printer' set in settings.json and no CUPS default configured - "
                      "run `lpstat -p -d` to see available printers.")
            self.show_result(self.status_frame("Print failed"), hold_seconds=2)

    # ------------------------------------------------------------
    # Voice-prompted AI edit ("Speak" button: hold to record, release to send)
    # ------------------------------------------------------------

    def get_nanobanana_client(self):
        if self.nanobanana_client is None:
            self.nanobanana_client = NanobananaClient(
                api_key_env=self.nanobanana_settings.get("api_key_env", "GOOGLE_API_KEY"),
                transcribe_model=self.nanobanana_settings.get("transcribe_model", "gemini-2.5-flash"),
                edit_model=self.nanobanana_settings.get("edit_model", "gemini-2.5-flash-image"),
            )
        return self.nanobanana_client

    def status_frame(self, text):
        base = self.finder if self.finder is not None else Image.new("RGB", (480, 320), (0, 0, 0))
        frame = base.copy()
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, frame.height // 2 - 25, frame.width, frame.height // 2 + 25), fill=(0, 0, 0))
        draw.text((frame.width // 2, frame.height // 2), text, font=self.medium_font, fill=(255, 255, 255), anchor="mm")
        return frame

    def show_result(self, img, hold_seconds):
        """Draws img and holds it on screen for a while, staying responsive to Stop/window-close."""
        self.screen.draw(img)
        end_time = time.time() + hold_seconds
        while self.running and not self.screen.quit_requested and time.time() < end_time:
            self.screen.update()
            time.sleep(0.05)

    def start_voice_prompt(self):
        if self.ai_pending:
            return
        try:
            self.audio_recorder.start(self.audio_path)
        except Exception as e:
            print(f"Could not start recording: {e}")
            self.show_result(self.status_frame("Mic error"), hold_seconds=2)
            return
        self.screen.draw(self.status_frame("Recording... release to send"))

    def finish_voice_prompt(self):
        if self.ai_pending:
            self.audio_recorder.stop()
            return

        audio_path = self.audio_recorder.stop()
        if audio_path is None:
            self.show_result(self.status_frame("No audio captured"), hold_seconds=2)
            return

        still_path = self.save_dir / "ai_source.jpg"
        self.picam2.switch_mode_and_capture_file(self.still_config, str(still_path))

        self.ai_pending = True
        self.ai_done.clear()
        Thread(target=self.run_ai_edit, args=(audio_path, still_path), daemon=True).start()

    def run_ai_edit(self, audio_path, still_path):
        """Runs on a background thread so the viewfinder/buttons stay responsive while waiting on the network."""
        try:
            client = self.get_nanobanana_client()
            prompt_text = client.transcribe(audio_path.read_bytes())
            if not prompt_text:
                self.ai_result = ("status", "Didn't catch that")
            else:
                print(f"Voice prompt: {prompt_text}")
                edited_bytes = client.edit_image(still_path.read_bytes(), prompt_text)
                if edited_bytes is None:
                    self.ai_result = ("status", "No image returned")
                else:
                    self.ai_result = ("image", edited_bytes, prompt_text)
        except Exception as e:
            print(f"AI edit failed: {e}")
            self.ai_result = ("status", "AI edit failed")
        finally:
            self.ai_done.set()

    def finish_ai_edit(self):
        self.ai_pending = False
        result = self.ai_result
        self.ai_result = None
        self.ai_done.clear()

        if result is None:
            return

        if result[0] == "status":
            self.show_result(self.status_frame(result[1]), hold_seconds=2)
            return

        _, image_bytes, prompt_text = result
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = self.save_dir / f"ai_{ts}.jpg"
        out_path.write_bytes(image_bytes)
        self.last_photo_path = out_path
        print(f"Saved {out_path} (prompt: {prompt_text!r})")

        result_img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((480, 320))
        self.show_result(result_img, hold_seconds=self.nanobanana_settings.get("result_hold_seconds", 4))

    def request_next_frame(self):
        self.pending_job = self.picam2.capture_request(
            wait=False,
            signal_function=lambda job: self.frame_ready.set()
        )

    def process_frame(self):

        dirty = False

        if self.frame_ready.is_set():
            self.frame_ready.clear()
            request = self.picam2.wait(self.pending_job)
            frame = request.make_array("main")
            request.release()

            self.finder = Image.fromarray(frame, "RGB")

            dirty = True

            self.request_next_frame()

        if self.screen.update():
            dirty = True

        if self.remote_photo_requested.is_set():
            self.remote_photo_requested.clear()
            if not self.ai_pending:
                self.save_image()

        if self.remote_speak_down.is_set():
            self.remote_speak_down.clear()
            self.start_voice_prompt()

        if self.remote_speak_up.is_set():
            self.remote_speak_up.clear()
            self.finish_voice_prompt()

        if self.ai_pending and self.ai_done.is_set():
            self.finish_ai_edit()
            dirty = True

        if dirty:
            if self.ai_pending:
                self.screen.draw(self.status_frame("Processing..."))
            elif self.finder is not None:
                self.screen.draw(self.finder)

    def run(self):
        self.running = True
        try:
            while self.running:

                self.process_frame()

                if self.screen.quit_requested:
                    return

                key = self.kbd.get_key()
                if key:
                    if key.lower() == "q":
                        return
                    elif key == " ":
                        self.save_image()

        except KeyboardInterrupt:
            pass
        finally:
            print("System stopping: tidying up")
            if self.shutter_remote is not None:
                self.shutter_remote.stop()
            self.screen.close()
            self.kbd.close()
            self.picam2.stop()


def main():
    magic_camera = MagicCamera()
    magic_camera.run()


if __name__ == "__main__":
    main()
