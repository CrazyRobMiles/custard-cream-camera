import json
import queue
import select
import sys
import termios
import time
import tty
from pathlib import Path
from threading import Event

from PIL import Image, ImageDraw, ImageFont

# review_station.py plus the displays/publishers/transcription packages and
# NanoBananaClient.py/print_overlays.py/ftp_server.py all live in ./lib, next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from displays import Button, create_display
from review_station import ReviewStationMixin
from transcription import create_transcriber

SETTINGS_PATH = Path(__file__).parent / "settings.json"


def load_settings():
    with open(SETTINGS_PATH) as f:
        return json.load(f)


# ------------------------------------------------------------
# Keyboard handling (non-blocking)
# ------------------------------------------------------------

class Keyboard:
    def __init__(self):
        # Launched from a desktop icon (Terminal=false), stdin isn't a real
        # TTY, so termios setup would raise - keyboard shortcuts just aren't
        # available in that case, since touch/the shutter remote cover it.
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


class CustardCreamCamera(ReviewStationMixin):
    """Two home screens, picked by settings.json's "mode":

    - "camera" (self.has_camera=True): a live Picamera2 viewfinder with Capture/Play modes.
    - "ftp" (self.has_camera=False): no camera - photos arrive over FTP (see lib/ftp_server.py)
      and the app is always in Play/play_grid, starting on a "waiting for photos" placeholder.

    Either way, reviewing/printing/publishing/voice-editing photos already in save_dir is the
    same shared ReviewStationMixin logic - see lib/review_station.py.
    """

    def __init__(self):
        settings = load_settings()
        self.settings = settings
        self.app_dir = Path(__file__).resolve().parent
        self.has_camera = settings.get("mode", "camera") == "camera"

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

        # The Play menu's four-across row (and other narrow multi-button rows) need a smaller
        # legend than the wider buttons that also use medium_font - this doesn't affect them.
        self.play_button_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26
        )
        self.phrase_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
        )

        # Created before the preview config below, since the preview capture size follows
        # self.screen.WIDTH/HEIGHT (the logical canvas size, configurable via settings["display"]
        # - see displays/__init__.py) rather than a hardcoded resolution.
        self.screen = create_display(settings)

        self.audio_output_settings = settings.get("audio_output", {})

        self.kbd = Keyboard()

        button_y = self.screen.HEIGHT - 50
        arrow_y = 40 + (self.screen.HEIGHT - 40 - 50 - 100) // 2

        if self.has_camera:
            # picamera2/libcamera and the shutter-remote modules are only importable on a device
            # with the Pi camera stack/hardware actually installed - never attempted in FTP mode.
            from libcamera import Transform
            from picamera2 import Picamera2
            from serial_shutter_remote import SerialShutterRemote
            from shutter_remote import ShutterRemote

            self.picam2 = Picamera2()

            # Corrects for the sensor being mounted rotated 180 degrees in this build - flip both
            # axes rather than rotating every captured frame in software afterward.
            camera_settings = settings.get("camera", {})
            camera_transform = Transform(
                hflip=camera_settings.get("hflip", False),
                vflip=camera_settings.get("vflip", False),
            )

            self.preview_config = self.picam2.create_preview_configuration(
                main={"size": (self.screen.WIDTH, self.screen.HEIGHT), "format": "BGR888"},
                transform=camera_transform,
            )

            self.still_config = self.picam2.create_still_configuration(
                main={"size": (4056, 3040), "format": "BGR888"},
                transform=camera_transform,
            )

            self.picam2.configure(self.preview_config)
            self.picam2.start()

            # Exposure compensation via the on-screen +/- buttons, for backlit subjects etc. The
            # libcamera "ExposureValue" control (the "correct" way to bias AE without disabling it)
            # turned out to be a no-op on this camera/tuning stack - confirmed by watching the
            # on-screen shutter-speed readout while pressing the buttons and seeing it never move -
            # so instead this snapshots the AE-computed ExposureTime/AnalogueGain as a baseline the
            # moment EV moves off zero (see exposure_baseline below) and explicitly scales
            # ExposureTime by 2**ev from that baseline, handing control back to AE at EV 0.
            exposure_settings = settings.get("exposure", {})
            self.ev_step = exposure_settings.get("step", 0.5)
            self.ev_min = exposure_settings.get("min", -2.0)
            self.ev_max = exposure_settings.get("max", 2.0)
            self.exposure_value = exposure_settings.get("default", 0.0)
            # (exposure_time_us, analogue_gain) captured from AE right as EV last moved off zero -
            # every subsequent adjustment scales from this fixed point rather than the live reading,
            # since once AE is disabled the live reading is just our own last override, not a fresh
            # measurement - reading from it again would compound drift on repeated presses instead
            # of giving a clean, repeatable +/- N stops from where AE actually metered the scene.
            self.exposure_baseline = None

            self.frame_ready = Event()
            self.request_next_frame()

            # Capture mode: live viewfinder, take a photo or switch to Play mode to review/act on
            # existing ones. There's no on-screen quit button any more - use keyboard 'q', or
            # Escape/window-close on the HDMI backends.
            self.capture_menu = (
                *self._row_of_buttons(button_y, 50, (
                    ("Click", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.save_image),
                    ("Play", self.medium_font, (255, 255, 255), (0, 90, 150), None, self.enter_play),
                )),
                # Exposure compensation - tucked into the top corners since the bottom row is full.
                Button(0, 0, 50, 40, "EV-", self.small_font, (255, 255, 255), (60, 60, 60), None, lambda: self.adjust_exposure(-self.ev_step)),
                Button(self.screen.WIDTH - 50, 0, 50, 40, "EV+", self.small_font, (255, 255, 255), (60, 60, 60), None, lambda: self.adjust_exposure(self.ev_step)),
            )

            # Play mode: reviews/acts on captures/ directly - Print/Speak/Publish always target
            # whatever's currently selected (self.play_index), no separate "choose, then act" step.
            # Left/Right step through images one at a time; Page opens a 3x3 grid to jump further.
            self.play_menu = (
                *self._row_of_buttons(button_y, 50, (
                    ("Capture", self.play_button_font, (255, 255, 255), (0, 0, 0), None, self.enter_capture),
                    ("Print", self.play_button_font, (255, 255, 255), (90, 90, 90), None, self.play_print),
                    ("Speak", self.play_button_font, (255, 255, 255), (0, 110, 0), self.finish_play_voice_prompt, self.start_voice_prompt),
                    ("Publish", self.play_button_font, (255, 255, 255), (150, 90, 0), None, self.show_publish_menu),
                )),
                Button(0, 0, 50, 40, "Stop", self.small_font, (255, 255, 255), (150, 30, 30), None, self.quit_app),
                Button(self.screen.WIDTH - 50, 0, 50, 40, "Page", self.small_font, (255, 255, 255), (60, 60, 60), None, self.show_play_grid),
                Button(0, arrow_y, 32, 100, "<", self.small_font, (255, 255, 255), (60, 60, 60), None, self.play_prev_image),
                Button(self.screen.WIDTH - 32, arrow_y, 32, 100, ">", self.small_font, (255, 255, 255), (60, 60, 60), None, self.play_next_image),
            )

            self.screen.set_buttons(self.capture_menu)
        else:
            # No "Capture" button - there's no other mode to switch to, since this app never
            # captures anything itself in FTP mode.
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

        # Printing ("Print" button) - printFile() only confirms the job was queued with CUPS,
        # not that it actually came out (paper jams/empty trays fail later, asynchronously), so
        # the real submit-and-watch work runs on a background thread the same way publish/AI
        # edit do, for the same reason (network/hardware I/O shouldn't block the viewfinder).
        self.print_pending = False
        self.print_done = Event()
        self.print_result = None
        # Set periodically by wait_for_print_job() from `lpstat -t` output while a print is in
        # flight, so the on-screen "Printing..." banner can show real diagnostic text (paper
        # out, offline, etc.) instead of a static placeholder - print_status_ready forces a
        # redraw the same way ai_status_ready does for the AI edit progress text.
        self.print_status_text = None
        self.print_status_ready = Event()

        self.watermark_settings = settings.get("watermark", {})
        self.datestamp_settings = settings.get("datestamp", {})

        self.finder = None
        self.last_metadata = None
        self.img = None
        self.running = None
        self.save_file_name = None
        self.last_photo_path = None

        # mode is one of "capture", "play", "play_grid" - "capture" only ever applies in camera
        # mode. play_view holds whatever the current single-image/grid frame is, drawn in place
        # of the live viewfinder while in Play mode. play_images/play_index track the review
        # position - Print/Speak/Publish always act on play_images[play_index], no separate
        # "choose, then act" step.
        self.mode = "capture" if self.has_camera else "play"
        self.play_images = []
        self.play_index = 0
        self.play_page = 0
        self.play_view = None
        # Maps a saved ai_<timestamp>.jpg Path to the voice instruction that produced it, so
        # Publish can send it along as the picture's aiInstruction (see finish_ai_edit()/
        # run_publish()). Only populated for the current session - edits from a previous run
        # have no entry, which is fine, since the text was never persisted anywhere else either.
        self.ai_prompts_by_path = {}

        # Voice-prompted AI edit ("Speak" button)
        custard_cream_settings = settings.get("custard_cream", {})
        self.custard_cream_settings = custard_cream_settings
        self.custard_cream_client = None
        self.transcriber = create_transcriber(settings, self.get_custard_cream_client)
        self.ai_pending = False
        self.ai_done = Event()
        self.ai_result = None
        # The still image being edited - set once by finish_voice_prompt(), read by both the
        # transcribe and edit phases below.
        self.ai_still_path = None
        # Result of the transcribe-only phase (run_transcribe()) - process_frame() picks this up
        # and runs the confirm/edit review (review_ai_prompt()) on the main thread once it's set.
        self.ai_transcript = None
        self.ai_transcribe_done = Event()
        # Set by run_transcribe()/run_ai_edit() as each stage starts/finishes, so the on-screen
        # banner can show real progress ("Transcribing...", "Sending image for processing...",
        # "Received result, saving...") instead of a static placeholder - ai_status_ready forces
        # a redraw the same way print_status_ready does for the print diagnostics.
        self.ai_status_text = None
        self.ai_status_ready = Event()
        # Set while the Speak button is held. voice_partial_text is updated live by
        # streaming transcribers (e.g. Vosk) via _on_voice_partial(); batch transcribers
        # (e.g. Gemini) never update it, leaving the static "Recording..." banner shown.
        self.voice_recording = False
        self.voice_partial_text = None
        self.voice_partial_ready = Event()

        # Publishing ("Publish" button) - pluggable, see publishers/. All configured destinations
        # are active at once; Publish opens a menu to choose which one this photo goes to, one at
        # a time (publishing to several means pressing Publish again afterwards for each one).
        # Publisher instances are lazily created and cached per type, since each needs API
        # credentials that may not be configured if that particular destination isn't used, and
        # publish() runs on a background thread the same way the AI edit does, for the same reason
        # (network I/O shouldn't block the viewfinder/buttons).
        self.publishers = {}
        self.publish_pending = False
        self.publish_done = Event()
        self.publish_result = None
        # Set when a publish succeeds against a backend (like custard-cream-server) that hands
        # back a {"url", "phrase"} result - lets finish_publish() show a QR code + phrase instead
        # of the plain text banner used for Flickr/Bluesky.
        self.publish_qr_result = None

        if self.has_camera:
            # Shutter remotes - Bluetooth and/or wired USB-serial, either or both can be enabled at
            # once (see settings.json's "shutter_remote"/"serial_remote" blocks). The Bluetooth
            # remote's physical button sends a real press+release, so its "speak" key drives
            # hold-to-talk the same way the on-screen Speak button does; the wired remote only ever
            # sends a single-shot "click", so it's wired to remote_photo_requested only, the same
            # event the Bluetooth remote's photo_key sets. All the Events below are set from a
            # remote's background listener thread and only ever acted on in process_frame(), on the
            # main thread, since drawing/Picamera2 calls aren't safe to make from a background thread.
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

            serial_remote_settings = settings.get("serial_remote", {})
            self.serial_remote = None
            if serial_remote_settings.get("enabled", False):
                self.serial_remote = SerialShutterRemote(
                    port=serial_remote_settings.get("port", "/dev/ttyUSB0"),
                    on_click=self.remote_photo_requested.set,
                    baud_rate=serial_remote_settings.get("baud_rate", 9600),
                )
                self.serial_remote.start()
        else:
            from ftp_server import FTPReceiver

            # FTP receiver - runs on its own background thread; on_file_received() (see
            # lib/ftp_server.py) flattens each completed upload into save_dir and queues its Path
            # here for process_frame() to pick up on the main thread.
            self.incoming_queue = queue.Queue()
            self.ftp_receiver = FTPReceiver(settings.get("ftp", {}), self.save_dir, self.incoming_queue)
            self.ftp_receiver.start()

            # Picks up anything already in save_dir (e.g. left over from a previous run) and shows
            # the newest, or the "waiting for photos" placeholder if there's nothing yet.
            self.enter_play()

    # ------------------------------------------------------------
    # ReviewStationMixin hooks - the only mode-specific seams in the shared Play/Publish/Speak/
    # Print flow (see lib/review_station.py)
    # ------------------------------------------------------------

    def _capture_fresh_still(self):
        """Used by finish_voice_prompt() when the remote's speak key triggers an edit directly
        from Capture mode, bypassing Play mode entirely - there's no existing photo to reuse, so
        this captures one fresh, the same way save_image() does for a normal photo. Only reachable
        in camera mode - nothing sets remote_speak_up without a shutter remote."""
        still_path = self.save_dir / "ai_source.jpg"
        self.picam2.switch_mode_and_capture_file(self.still_config, str(still_path))
        print(f"Speak: captured fresh photo {still_path}")
        return still_path

    def _non_play_menu(self):
        return self.capture_menu if self.has_camera else self.play_menu

    def _empty_play_buttons(self, button_y):
        if not self.has_camera:
            return ()
        return (
            Button(0, button_y, self.screen.WIDTH, 50, "Capture", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.enter_capture),
        )

    def _empty_play_message(self):
        return "No photos yet" if self.has_camera else "Waiting for photos..."

    def adjust_exposure(self, delta):
        new_value = round(min(self.ev_max, max(self.ev_min, self.exposure_value + delta)), 2)
        if new_value == self.exposure_value:
            return
        self.exposure_value = new_value

        if self.exposure_value == 0:
            self.exposure_baseline = None
            self.picam2.set_controls({"AeEnable": True})
            return

        if self.exposure_baseline is None:
            metadata = self.last_metadata or {}
            base_exposure = metadata.get("ExposureTime")
            base_gain = metadata.get("AnalogueGain")
            if not base_exposure:
                # No AE reading available yet (shouldn't normally happen - the viewfinder is
                # already streaming by the time buttons are enabled) - nothing to scale from.
                self.exposure_value -= delta
                return
            self.exposure_baseline = (base_exposure, base_gain)

        base_exposure, base_gain = self.exposure_baseline
        new_exposure = int(base_exposure * (2 ** self.exposure_value))
        exp_min, exp_max, _ = self.picam2.camera_controls["ExposureTime"]
        new_exposure = max(exp_min, min(exp_max, new_exposure))

        controls = {"AeEnable": False, "ExposureTime": new_exposure}
        if base_gain:
            controls["AnalogueGain"] = base_gain
        self.picam2.set_controls(controls)

    def save_image(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.save_file_name = self.save_dir / f"capture_{ts}.jpg"
        self.picam2.switch_mode_and_capture_file(self.still_config, str(self.save_file_name))
        self.last_photo_path = self.save_file_name
        print(f"Saved {self.save_file_name}")

        # Flash the screen white and play a shutter sound, briefly - the shutter remote/keyboard
        # triggers have no other feedback, so this makes it obvious a photo was actually taken.
        shutter_sound = self.audio_output_settings.get("shutter_sound")
        if shutter_sound:
            self.play_sound(self.app_dir / shutter_sound)
        white_frame = Image.new("RGB", (self.screen.WIDTH, self.screen.HEIGHT), (255, 255, 255))
        self.show_result(white_frame, hold_seconds=0.5)

    # ------------------------------------------------------------
    # Capture mode <-> Play mode (camera mode only)
    # ------------------------------------------------------------

    def enter_capture(self):
        self.mode = "capture"
        self.screen.set_buttons(self.capture_menu)
        if self.finder is not None:
            self.screen.draw(self.live_frame())

    def quit_app(self):
        """"Stop" in the play menu - the only on-screen way to exit cleanly when launched from
        the desktop icon, where there's no keyboard or window chrome available."""
        self.running = False

    def live_frame(self):
        """The current viewfinder frame, with the EV setting and actual metered shutter speed/
        gain overlaid - showing the real numbers (not just the EV setting) so it's obvious
        whether the exposure compensation buttons are actually reaching the AE algorithm.
        """
        frame = self.finder.copy()
        draw = ImageDraw.Draw(frame)

        metadata = self.last_metadata or {}
        exposure_us = metadata.get("ExposureTime")
        gain = metadata.get("AnalogueGain")

        parts = [f"EV {self.exposure_value:+.1f}"]
        if exposure_us:
            parts.append(f"1/{round(1_000_000 / exposure_us)}s")
        if gain:
            parts.append(f"gain {gain:.2f}x")

        draw.text((frame.width // 2, 20), "  ".join(parts), font=self.small_font, fill=(255, 255, 0), anchor="mm")
        return frame

    def request_next_frame(self):
        self.pending_job = self.picam2.capture_request(
            wait=False,
            signal_function=lambda job: self.frame_ready.set()
        )

    def process_frame(self):

        dirty = False

        if self.has_camera:
            if self.frame_ready.is_set():
                self.frame_ready.clear()
                request = self.picam2.wait(self.pending_job)
                frame = request.make_array("main")
                self.last_metadata = request.get_metadata()
                request.release()

                self.finder = Image.fromarray(frame, "RGB")

                if self.mode == "capture":
                    dirty = True

                self.request_next_frame()

        if self.screen.update():
            dirty = True

        if self.has_camera:
            if self.remote_photo_requested.is_set():
                self.remote_photo_requested.clear()
                if not self.ai_pending:
                    # In Play mode the physical shutter button switches back to Capture without
                    # taking a photo - it shouldn't blindly capture whatever the camera happens to
                    # be pointed at while you're mid-review of past photos.
                    if self.mode in ("play", "play_grid"):
                        self.enter_capture()
                    else:
                        self.save_image()

            if self.remote_speak_down.is_set():
                self.remote_speak_down.clear()
                self.start_voice_prompt()

            if self.remote_speak_up.is_set():
                self.remote_speak_up.clear()
                self.finish_voice_prompt()
        else:
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
                    # small_font: an lpstat detail line ("Sending CYAN plane", "No paper tray
                    # loaded, aborting!") runs longer than the couple of words medium_font (the
                    # default) is sized for.
                    self.screen.draw(self.status_frame(self.print_status_text, font=self.small_font))
                else:
                    self.screen.draw(self.status_frame("Printing..."))
            elif self.mode in ("play", "play_grid"):
                self.screen.draw(self.play_view)
            elif self.finder is not None:
                self.screen.draw(self.live_frame())

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
                    elif key == " " and self.has_camera:
                        # Same "switch to Capture rather than shoot blind" rule as the physical
                        # shutter remote - see the equivalent branch in process_frame().
                        if self.mode in ("play", "play_grid"):
                            self.enter_capture()
                        else:
                            self.save_image()

                if not self.has_camera:
                    # Nothing paces this loop in FTP mode the way frame_ready does in camera
                    # mode - avoid spinning at full CPU polling an empty queue.
                    time.sleep(0.02)

        except KeyboardInterrupt:
            pass
        finally:
            print("System stopping: tidying up")
            if self.has_camera:
                if self.shutter_remote is not None:
                    self.shutter_remote.stop()
                if self.serial_remote is not None:
                    self.serial_remote.stop()
                self.picam2.stop()
            else:
                self.ftp_receiver.stop()
            self.screen.close()
            self.kbd.close()


def main():
    custard_cream_camera = CustardCreamCamera()
    custard_cream_camera.run()


if __name__ == "__main__":
    main()
