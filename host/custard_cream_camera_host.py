import json
import queue
import select
import sys
import termios
import time
import tty
from pathlib import Path
from threading import Event

from PIL import ImageFont

# Shared with the camera app (see camera/custard_cream_camera.py) - review_station.py plus the
# displays/publishers/transcription packages and NanoBananaClient.py/print_overlays.py all live
# in ../lib, one level up from this app's own folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from displays import Button, create_display
from review_station import ReviewStationMixin
from transcription import create_transcriber

from ftp_server import FTPReceiver

SETTINGS_PATH = Path(__file__).parent / "settings.json"


def load_settings():
    with open(SETTINGS_PATH) as f:
        return json.load(f)


# ------------------------------------------------------------
# Keyboard handling (non-blocking) - convenience for testing on a desktop backend; not needed
# for a real deployment with no keyboard attached (use the on-screen "Stop" button instead).
# ------------------------------------------------------------

class Keyboard:
    def __init__(self):
        self.enabled = sys.stdin.isatty()
        if self.enabled:
            self.fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)

    def get_key(self):
        if not self.enabled:
            return None
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def close(self):
        if self.enabled:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


class CustardCreamCameraHost(ReviewStationMixin):
    """Receives JPEGs over FTP (from e.g. a Sony camera's FTP-transfer feature) and gives them
    the same review/print/publish/voice-edit treatment as the camera app's Play mode - see
    lib/review_station.py for that shared logic. There is no camera and no other mode: this app
    is always in "play"/"play_grid", starting on a "waiting for photos" placeholder until the
    first FTP upload arrives.
    """

    def __init__(self):
        settings = load_settings()
        self.settings = settings
        self.app_dir = Path(__file__).resolve().parent

        self.small_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
        )
        self.medium_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
        )
        self.large_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48
        )
        # The Play menu's four-across row (and other narrow multi-button rows) need a smaller
        # legend than the wider buttons that also use medium_font - this doesn't affect them.
        self.play_button_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26
        )
        self.phrase_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
        )

        self.screen = create_display(settings)
        self.kbd = Keyboard()

        self.audio_output_settings = settings.get("audio_output", {})

        button_y = self.screen.HEIGHT - 50
        arrow_y = 40 + (self.screen.HEIGHT - 40 - 50 - 100) // 2

        # No "Capture" button - there's no other mode to switch to, since this app never
        # captures anything itself.
        self.play_menu = (
            *self._row_of_buttons(button_y, 50, (
                ("Print", self.play_button_font, (255, 255, 255), (90, 90, 90), None, self.play_print),
                ("Speak", self.play_button_font, (255, 255, 255), (0, 110, 0), self.finish_play_voice_prompt, self.start_voice_prompt),
                ("Publish", self.play_button_font, (255, 255, 255), (150, 90, 0), None, self.show_publish_menu),
            )),
            Button(0, 0, 50, 40, "Stop", self.small_font, (255, 255, 255), (150, 30, 30), None, self.quit_app),
            Button(self.screen.WIDTH - 50, 0, 50, 40, "Page", self.small_font, (255, 255, 255), (60, 60, 60), None, self.show_play_grid),
            Button(0, arrow_y, 32, 100, "<", self.small_font, (255, 255, 255), (60, 60, 60), None, self.play_prev_image),
            Button(self.screen.WIDTH - 32, arrow_y, 32, 100, ">", self.small_font, (255, 255, 255), (60, 60, 60), None, self.play_next_image),
        )

        self.save_dir = Path("captures")
        self.save_dir.mkdir(exist_ok=True)

        printing_settings = settings.get("printing", {})
        self.printing_settings = printing_settings
        self.printer_name = printing_settings.get("printer")
        self.print_test_mode = printing_settings.get("test_mode", False)
        self.print_test_dir = Path(printing_settings.get("test_folder", "print_tests"))
        if self.print_test_mode:
            self.print_test_dir.mkdir(exist_ok=True)

        self.print_pending = False
        self.print_done = Event()
        self.print_result = None
        self.print_status_text = None
        self.print_status_ready = Event()

        self.watermark_settings = settings.get("watermark", {})
        self.datestamp_settings = settings.get("datestamp", {})

        self.running = None
        self.last_photo_path = None

        # Always "play" or "play_grid" - see the class docstring.
        self.mode = "play"
        self.play_images = []
        self.play_index = 0
        self.play_page = 0
        self.play_view = None
        self.ai_prompts_by_path = {}

        custard_cream_settings = settings.get("custard_cream", {})
        self.custard_cream_settings = custard_cream_settings
        self.custard_cream_client = None
        self.transcriber = create_transcriber(settings, self.get_custard_cream_client)
        self.ai_pending = False
        self.ai_done = Event()
        self.ai_result = None
        self.ai_still_path = None
        self.ai_transcript = None
        self.ai_transcribe_done = Event()
        self.ai_status_text = None
        self.ai_status_ready = Event()
        self.voice_recording = False
        self.voice_partial_text = None
        self.voice_partial_ready = Event()

        self.publishers = {}
        self.publish_pending = False
        self.publish_done = Event()
        self.publish_result = None
        self.publish_qr_result = None

        # FTP receiver - runs on its own background thread; on_file_received() (see
        # ftp_server.py) flattens each completed upload into save_dir and queues its Path here
        # for process_frame() to pick up on the main thread.
        self.incoming_queue = queue.Queue()
        self.ftp_receiver = FTPReceiver(settings.get("ftp", {}), self.save_dir, self.incoming_queue)
        self.ftp_receiver.start()

        # Picks up anything already in save_dir (e.g. left over from a previous run) and shows
        # the newest, or the "waiting for photos" placeholder if there's nothing yet.
        self.enter_play()

    # ------------------------------------------------------------
    # ReviewStationMixin hooks - see lib/review_station.py. _capture_fresh_still() and
    # _non_play_menu() are never reached (there's no camera, and this app has no mode other
    # than "play"/"play_grid" for review_ai_prompt() to fall back to), so their base-class
    # defaults are fine as-is; only the empty-Play-mode message is worth overriding.
    # ------------------------------------------------------------

    def _empty_play_message(self):
        return "Waiting for photos..."

    def quit_app(self):
        """"Stop" in the play menu - the only on-screen way to exit cleanly when launched from
        the desktop icon, where there's no keyboard or window chrome available."""
        self.running = False

    def process_frame(self):
        dirty = False

        if self.screen.update():
            dirty = True

        while True:
            try:
                new_path = self.incoming_queue.get_nowait()
            except queue.Empty:
                break
            self._show_new_photo(new_path)
            dirty = True

        if self.voice_partial_ready.is_set():
            self.voice_partial_ready.clear()
            dirty = True

        if self.ai_status_ready.is_set():
            self.ai_status_ready.clear()
            dirty = True

        if self.print_status_ready.is_set():
            self.print_status_ready.clear()
            dirty = True

        if self.ai_pending and self.ai_transcribe_done.is_set():
            self.review_ai_prompt()
            dirty = True

        if self.ai_pending and self.ai_done.is_set():
            self.finish_ai_edit()
            dirty = True

        if self.publish_pending and self.publish_done.is_set():
            self.finish_publish()
            dirty = True

        if self.print_pending and self.print_done.is_set():
            self.finish_print()
            dirty = True

        if dirty:
            if self.voice_recording:
                self.screen.draw(self.status_frame(self.voice_partial_text or "Recording... release to send"))
            elif self.ai_pending:
                self.screen.draw(self.status_frame(self.ai_status_text or "Processing..."))
            elif self.publish_pending:
                self.screen.draw(self.status_frame("Publishing..."))
            elif self.print_pending:
                if self.print_status_text:
                    self.screen.draw(self.status_frame(self.print_status_text, font=self.small_font))
                else:
                    self.screen.draw(self.status_frame("Printing..."))
            elif self.mode in ("play", "play_grid"):
                self.screen.draw(self.play_view)

    def run(self):
        self.running = True
        try:
            while self.running:
                self.process_frame()

                if self.screen.quit_requested:
                    return

                key = self.kbd.get_key()
                if key and key.lower() == "q":
                    return

                time.sleep(0.02)

        except KeyboardInterrupt:
            pass
        finally:
            print("System stopping: tidying up")
            self.ftp_receiver.stop()
            self.screen.close()
            self.kbd.close()


def main():
    host = CustardCreamCameraHost()
    host.run()


if __name__ == "__main__":
    main()
