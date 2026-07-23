import io
import json
import select
import shutil
import subprocess
import sys
import tempfile
import termios
import time
import tty
from pathlib import Path
from threading import Event, Thread

import cups
import qrcode
from libcamera import Transform
from PIL import Image, ImageDraw, ImageFont
from picamera2 import Picamera2

from displays import Button, create_display
from NanoBananaClient import CustardCreamClient
from print_overlays import apply_datestamp, apply_watermark
from publishers import available_publishers, create_publisher, publisher_label
from serial_shutter_remote import SerialShutterRemote
from shutter_remote import ShutterRemote
from transcription import create_transcriber

SETTINGS_PATH = Path(__file__).parent / "settings.json"

# IPP job-state values (RFC 8011 SS5.3.7) - pycups surfaces the raw int rather than named
# constants, so the ones this code checks for are spelled out here instead.
CUPS_JOB_STATE_CANCELED = 7
CUPS_JOB_STATE_ABORTED = 8
CUPS_JOB_STATE_COMPLETED = 9


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


class CustardCreamCamera():

    def __init__(self):
        settings = load_settings()
        self.settings = settings

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

        # The Play menu's four narrow (110px) buttons need a smaller legend than the
        # wider buttons that also use medium_font - this doesn't affect them.
        self.play_button_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26
        )
        self.phrase_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
        )

        self.picam2 = Picamera2()

        # Corrects for the sensor being mounted rotated 180 degrees in this build - flip both
        # axes rather than rotating every captured frame in software afterward.
        camera_settings = settings.get("camera", {})
        camera_transform = Transform(
            hflip=camera_settings.get("hflip", False),
            vflip=camera_settings.get("vflip", False),
        )

        self.preview_config = self.picam2.create_preview_configuration(
            main={"size": (480, 320), "format": "BGR888"},
            transform=camera_transform,
        )

        self.still_config = self.picam2.create_still_configuration(
            main={"size": (4056, 3040), "format": "BGR888"},
            transform=camera_transform,
        )

        self.picam2.configure(self.preview_config)
        self.picam2.start()

        self.audio_output_settings = settings.get("audio_output", {})

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

        self.kbd = Keyboard()

        self.screen = create_display(settings)

        button_y = self.screen.HEIGHT - 50

        # Capture mode: live viewfinder, take a photo or switch to Play mode to review/act on
        # existing ones. There's no on-screen quit button any more - use keyboard 'q', or
        # Escape/window-close on the HDMI backends.
        self.capture_menu = (
            Button(0, button_y, 230, 50, "Click", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.save_image),
            Button(250, button_y, 230, 50, "Play", self.medium_font, (255, 255, 255), (0, 90, 150), None, self.enter_play),
            # Exposure compensation - tucked into the top corners since the bottom row is full.
            Button(0, 0, 50, 40, "EV-", self.small_font, (255, 255, 255), (60, 60, 60), None, lambda: self.adjust_exposure(-self.ev_step)),
            Button(430, 0, 50, 40, "EV+", self.small_font, (255, 255, 255), (60, 60, 60), None, lambda: self.adjust_exposure(self.ev_step)),
        )

        # Play mode: reviews/acts on captures/ directly - Print/Speak/Publish always target
        # whatever's currently selected (self.play_index), no separate "choose, then act" step.
        # Left/Right step through images one at a time; Page opens a 3x3 grid to jump further.
        self.play_menu = (
            Button(0, button_y, 110, 50, "Capture", self.play_button_font, (255, 255, 255), (0, 0, 0), None, self.enter_capture),
            Button(123, button_y, 110, 50, "Print", self.play_button_font, (255, 255, 255), (90, 90, 90), None, self.play_print),
            Button(246, button_y, 110, 50, "Speak", self.play_button_font, (255, 255, 255), (0, 110, 0), up_handler=self.finish_play_voice_prompt, down_handler=self.start_voice_prompt),
            Button(369, button_y, 110, 50, "Publish", self.play_button_font, (255, 255, 255), (150, 90, 0), None, self.show_publish_menu),
            Button(0, 0, 50, 40, "Stop", self.small_font, (255, 255, 255), (150, 30, 30), None, self.quit_app),
            Button(430, 0, 50, 40, "Page", self.small_font, (255, 255, 255), (60, 60, 60), None, self.show_play_grid),
            Button(0, 110, 32, 100, "<", self.small_font, (255, 255, 255), (60, 60, 60), None, self.play_prev_image),
            Button(448, 110, 32, 100, ">", self.small_font, (255, 255, 255), (60, 60, 60), None, self.play_next_image),
        )

        self.screen.set_buttons(self.capture_menu)

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

        self.watermark_settings = settings.get("watermark", {})
        self.datestamp_settings = settings.get("datestamp", {})

        self.finder = None
        self.last_metadata = None
        self.img = None
        self.running = None
        self.save_file_name = None
        self.last_photo_path = None

        # mode is one of "capture", "play", "play_grid". play_view holds whatever the current
        # single-image/grid frame is, drawn in place of the live viewfinder while in Play mode.
        # play_images/play_index track the review position - Print/Speak/Publish always act on
        # play_images[play_index], no separate "choose, then act" step.
        self.mode = "capture"
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
        # Set by run_ai_edit() as soon as transcription comes back, so the "Processing..." status
        # can switch to showing the actual prompt while the (usually much slower) image edit
        # call is still in flight - ai_prompt_ready just forces a redraw at that moment, since
        # dirty otherwise only becomes true on user input or when the whole edit finishes.
        self.ai_prompt_text = None
        self.ai_prompt_ready = Event()
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

    def play_sound(self, path):
        """Best-effort audio playback via `aplay` - doesn't block the caller on the sound
        finishing, and never raises: a missing/misconfigured audio device (or no audio hardware
        at all) should mean silence, not a broken shutter button. A background thread still
        waits on it just to print `aplay`'s own error output if it fails, since otherwise a
        failure here is completely invisible - there'd be no sound and no clue why not.
        """
        if not self.audio_output_settings.get("enabled", True):
            return

        args = ["aplay", "-q"]
        device = self.audio_output_settings.get("device")
        if device:
            args += ["-D", device]
        args.append(str(path))

        try:
            process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError as e:
            print(f"Could not play sound {path}: {e}")
            return

        def wait_and_report():
            _, stderr = process.communicate()
            if process.returncode != 0:
                print(f"aplay failed (exit {process.returncode}) playing {path}: "
                      f"{stderr.decode(errors='replace').strip()}")

        Thread(target=wait_and_report, daemon=True).start()

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
            self.play_sound(Path(__file__).parent / shutter_sound)
        white_frame = Image.new("RGB", (self.screen.WIDTH, self.screen.HEIGHT), (255, 255, 255))
        self.show_result(white_frame, hold_seconds=0.5)

    def prepare_print_copy(self, path):
        """Returns a path to print: either `path` unchanged, or a temporary copy with the
        configured watermark/date stamp composited on top. Never modifies the original file.
        """
        watermark_on = self.watermark_settings.get("enabled", False)
        datestamp_on = self.datestamp_settings.get("enabled", False)
        if not (watermark_on or datestamp_on):
            return path

        img = Image.open(path).convert("RGB")

        if watermark_on:
            watermark_path = Path(__file__).parent / self.watermark_settings.get("file", "assets/images/watermark.png")
            try:
                img = apply_watermark(img, watermark_path, self.watermark_settings)
            except Exception as e:
                print(f"Could not apply watermark: {e}")

        if datestamp_on:
            try:
                img = apply_datestamp(img, self.datestamp_settings, Path(path).stat().st_mtime)
            except Exception as e:
                print(f"Could not apply date stamp: {e}")

        out_path = Path(tempfile.gettempdir()) / "custard_cream_camera_print.jpg"
        img.save(out_path, "JPEG", quality=95)
        return out_path

    def print_image(self, path=None):
        if self.print_pending:
            return

        path = path or self.last_photo_path
        if path is None:
            print("Nothing to print yet")
            self.show_result(self.status_frame("Nothing to print yet"), hold_seconds=2)
            self.show_play_image()
            return

        print_path = self.prepare_print_copy(path)

        if self.print_test_mode:
            # Exercises the full pipeline (watermark/date stamp included) without spending
            # paper/ink - saves what would have been sent to the printer instead of actually
            # sending it.
            ts = time.strftime("%Y%m%d_%H%M%S")
            test_path = self.print_test_dir / f"print_test_{ts}.jpg"
            shutil.copyfile(print_path, test_path)
            print(f"Print testing: saved {test_path} instead of printing")
            self.show_result(self.status_frame("Test print saved"), hold_seconds=2)
            self.show_play_image()
            return

        print(f"Printing {path}" + (f" (with overlays: {print_path})" if print_path != path else ""))
        self.print_pending = True
        self.print_done.clear()
        self.print_result = None
        Thread(target=self.run_print, args=(print_path,), daemon=True).start()

    def run_print(self, print_path):
        """Runs on a background thread: watching the job through to completion can take as long
        as the physical print itself (a minute or more on the CP400 dye-sub printer), so this
        can't block the viewfinder/buttons the way the old fire-and-forget `lp` call could.
        """
        try:
            conn = cups.Connection()
            printer_name = self.printer_name or conn.getDefault()
            if not printer_name:
                print("No 'printer' set in settings.json and no CUPS default configured - "
                      "run `lpstat -p -d` to see available printers.")
                self.print_result = "No printer configured"
                return

            self.reset_printer_queue(conn, printer_name)
            job_id = conn.printFile(printer_name, str(print_path), "Custard Cream Camera", {})
            self.print_result = self.wait_for_print_job(conn, job_id)
        except Exception as e:
            print(f"Print failed: {e}")
            self.print_result = "Print failed"
        finally:
            self.print_done.set()

    def reset_printer_queue(self, conn, printer_name):
        """Run before every print: a job that fails outright (e.g. an empty paper tray) leaves
        CUPS with a disabled, rejecting queue - every print after it just piles up in the spool
        instead of erroring, so nothing ever comes out even once the printer's fixed. Clearing
        the queue and re-enabling/accepting each time means a print either comes out now or
        fails loudly, instead of silently queuing behind a stuck printer.

        Uses the same CUPS connection as the job submission that follows, rather than shelling
        out to `cancel`/`cupsenable`/`cupsaccept` - which also sidesteps needing `sudo` for the
        latter two, since pycups authorizes these directly against the caller's `lpadmin` group
        membership (see docs/printer-cups-setup.md).
        """
        try:
            conn.cancelAllJobs(printer_name, purge_jobs=True)
            conn.enablePrinter(printer_name)
            conn.acceptJobs(printer_name)
        except cups.IPPError as e:
            print(f"Could not reset printer queue for {printer_name!r}: {e}")

    def wait_for_print_job(self, conn, job_id):
        """Polls a submitted job until CUPS reports it finished, one way or another, or a
        timeout elapses. printFile() only confirms the job was queued - without this, a print
        that fails downstream (out of paper, a jam) would look identical to one that actually
        came out.
        """
        timeout = self.printing_settings.get("job_timeout_seconds", 120)
        deadline = time.time() + timeout
        reasons = []

        while time.time() < deadline:
            try:
                attrs = conn.getJobAttributes(job_id)
            except cups.IPPError as e:
                print(f"Could not query print job {job_id}: {e}")
                return "Print status unknown"

            state = attrs.get("job-state")
            reasons = [r for r in attrs.get("job-state-reasons", []) if r != "none"]

            if state == CUPS_JOB_STATE_COMPLETED:
                return "Printed!"
            if state in (CUPS_JOB_STATE_CANCELED, CUPS_JOB_STATE_ABORTED):
                print(f"Print job {job_id} failed: {reasons}")
                message = attrs.get("job-printer-state-message") or (reasons[0] if reasons else None)
                return message or "Print failed"

            time.sleep(1)

        print(f"Print job {job_id} still not finished after {timeout}s (last reasons: {reasons})")
        return "Print taking longer than expected"

    def finish_print(self):
        self.print_pending = False
        message = self.print_result
        self.print_result = None
        self.print_done.clear()
        self.show_result(self.status_frame(message), hold_seconds=2)
        self.show_play_image()

    # ------------------------------------------------------------
    # Capture mode <-> Play mode
    # ------------------------------------------------------------

    def enter_capture(self):
        self.mode = "capture"
        self.screen.set_buttons(self.capture_menu)
        if self.finder is not None:
            self.screen.draw(self.live_frame())

    def quit_app(self):
        """"Stop" in the play menu - the only on-screen way to exit cleanly when launched from
        the desktop icon, where there's no keyboard or window chrome to quit with."""
        self.running = False

    def enter_play(self):
        """Always lands on the most recently taken photo - see show_play_image()."""
        if self.ai_pending or self.publish_pending or self.print_pending:
            return
        self.play_page = 0
        self.play_images = sorted(
            (p for p in self.save_dir.glob("*.jpg") if p.name != "ai_source.jpg"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        self.play_index = 0
        self.show_play_image()

    def show_play_image(self):
        """The main Play-mode view: one photo at a time, full screen. Print/Speak/Publish act
        directly on play_images[play_index] - no separate "choose, then act" step."""
        self.mode = "play"
        button_y = self.screen.HEIGHT - 50

        if not self.play_images:
            self.screen.set_buttons((
                Button(0, button_y, 480, 50, "Capture", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.enter_capture),
            ))
            self.play_view = self.status_frame("No photos yet")
            self.screen.draw(self.play_view)
            return

        path = self.play_images[self.play_index]
        try:
            self.play_view = Image.open(path).convert("RGB").resize((self.screen.WIDTH, self.screen.HEIGHT))
        except Exception as e:
            print(f"Could not load {path}: {e}")
            self.play_view = self.status_frame("Could not load photo")

        self.screen.set_buttons(self.play_menu)
        self.screen.draw(self.play_view)

    def play_prev_image(self):
        """"<" - steps to an older photo."""
        if self.play_index < len(self.play_images) - 1:
            self.play_index += 1
            self.show_play_image()

    def play_next_image(self):
        """">" - steps to a newer photo."""
        if self.play_index > 0:
            self.play_index -= 1
            self.show_play_image()

    def show_play_grid(self):
        """"Page" button - a 3x3 grid to jump further than one image at a time."""
        if self.ai_pending or self.publish_pending or self.print_pending or not self.play_images:
            return
        self.mode = "play_grid"
        button_y = self.screen.HEIGHT - 50

        self.screen.set_buttons(())
        self.screen.draw(self.status_frame("Loading..."))

        cols, rows = 3, 3
        per_page = cols * rows
        grid_height = button_y
        cell_w = self.screen.WIDTH // cols
        cell_h = grid_height // rows

        page_start = self.play_page * per_page
        page_images = self.play_images[page_start:page_start + per_page]

        canvas = Image.new("RGB", (self.screen.WIDTH, self.screen.HEIGHT), (20, 20, 20))
        thumb_buttons = []

        for i, path in enumerate(page_images):
            col, row = i % cols, i // cols
            cell_x, cell_y = col * cell_w, row * cell_h

            try:
                thumb = Image.open(path)
                thumb.draft("RGB", (cell_w, cell_h))  # fast DCT-scaled JPEG decode for thumbnailing
                thumb = thumb.convert("RGB")
                thumb.thumbnail((cell_w - 8, cell_h - 8))
                canvas.paste(thumb, (cell_x + (cell_w - thumb.width) // 2, cell_y + (cell_h - thumb.height) // 2))
            except Exception as e:
                print(f"Could not load thumbnail {path}: {e}")

            absolute_index = page_start + i
            thumb_buttons.append(Button(
                cell_x, cell_y, cell_w, cell_h, "", self.small_font, (0, 0, 0), (0, 0, 0),
                up_handler=None, down_handler=(lambda idx=absolute_index: self.select_play_grid_image(idx)), visible=False,
            ))

        self.play_view = canvas

        nav_buttons = (
            Button(0, button_y, 150, 50, "Left", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.play_grid_prev_page),
            Button(165, button_y, 150, 50, "Right", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.play_grid_next_page),
            Button(330, button_y, 150, 50, "Back", self.medium_font, (255, 255, 255), (90, 90, 90), None, self.show_play_image),
        )
        self.screen.set_buttons((*nav_buttons, *thumb_buttons))
        self.screen.draw(self.play_view)

    def select_play_grid_image(self, index):
        self.play_index = index
        self.show_play_image()

    def play_grid_prev_page(self):
        if self.play_page > 0:
            self.play_page -= 1
            self.show_play_grid()

    def play_grid_next_page(self):
        max_page = (len(self.play_images) - 1) // 9
        if self.play_page < max_page:
            self.play_page += 1
            self.show_play_grid()

    def play_print(self):
        if not self.play_images or self.print_pending:
            return
        self.print_image(self.play_images[self.play_index])

    def finish_play_voice_prompt(self):
        if not self.play_images:
            return
        self.finish_voice_prompt(image_path=self.play_images[self.play_index])

    # ------------------------------------------------------------
    # Publishing ("Publish" button, in Play mode)
    # ------------------------------------------------------------

    # Button colour per destination, shown in the publish menu - falls back to grey for any
    # publisher type not listed here.
    PUBLISH_MENU_COLOURS = {
        "flickr": (150, 90, 0),
        "bsky": (0, 133, 255),
        "custard_cream_server": (120, 90, 40),
    }

    def get_publisher(self, publisher_type):
        if publisher_type not in self.publishers:
            self.publishers[publisher_type] = create_publisher(self.settings, publisher_type)
        return self.publishers[publisher_type]

    def show_publish_menu(self):
        """"Publish" button in Play mode - choose which configured destination to send this photo
        to. Only one destination is published to per selection; to publish to several, press
        Publish again afterwards and pick another."""
        if not self.play_images or self.publish_pending or self.print_pending:
            return

        options = available_publishers(self.settings)
        if not options:
            self.show_result(self.status_frame("No publishers configured"), hold_seconds=2)
            self.show_play_image()
            return

        if len(options) == 1:
            # Only one destination enabled - skip the menu, there's nothing to choose between.
            self.start_publish(options[0][0])
            return

        button_y = self.screen.HEIGHT - 50
        buttons = [
            Button(i * 123, button_y, 110, 50, label, self.play_button_font, (255, 255, 255),
                   self.PUBLISH_MENU_COLOURS.get(publisher_type, (90, 90, 90)), None,
                   lambda publisher_type=publisher_type: self.start_publish(publisher_type))
            for i, (publisher_type, label) in enumerate(options)
        ]
        buttons.append(Button(len(options) * 123, button_y, 110, 50, "Back", self.play_button_font,
                               (255, 255, 255), (90, 90, 90), None, self.show_play_image))

        self.screen.set_buttons(tuple(buttons))
        self.screen.draw(self.play_view)

    def start_publish(self, publisher_type):
        if not self.play_images or self.publish_pending or self.print_pending:
            return
        self.publish_pending = True
        self.publish_done.clear()
        Thread(target=self.run_publish, args=(self.play_images[self.play_index], publisher_type), daemon=True).start()

    def run_publish(self, image_path, publisher_type):
        """Runs on a background thread so the viewfinder/buttons stay responsive while waiting on the network."""
        self.publish_qr_result = None
        label = publisher_label(publisher_type)
        try:
            publisher = self.get_publisher(publisher_type)
            ai_instruction = self.ai_prompts_by_path.get(image_path)
            ok = publisher.publish(image_path, ai_instruction=ai_instruction)
            self.publish_result = f"Published to {label}!" if ok else f"{label} publish failed"
            if ok:
                # Only custard-cream-server sets this - Flickr/Bluesky publishers have no such
                # attribute, so the plain text banner path below is unaffected for them.
                self.publish_qr_result = getattr(publisher, "last_result", None)
        except Exception as e:
            print(f"Publish to {label} failed: {e}")
            self.publish_result = f"{label} publish failed"
        finally:
            self.publish_done.set()

    def finish_publish(self):
        self.publish_pending = False
        message = self.publish_result
        qr_result = self.publish_qr_result
        self.publish_result = None
        self.publish_qr_result = None
        self.publish_done.clear()

        if qr_result:
            # The QR/phrase screen is dismissed by hand (there's no telling how long someone
            # needs to get their phone out and scan it), unlike the plain text banners below.
            frame = self.qr_result_frame(qr_result["url"], qr_result["phrase"])
            self.show_result_until_done(frame)
        else:
            self.show_result(self.status_frame(message), hold_seconds=2)

        self.show_play_image()

    # ------------------------------------------------------------
    # Voice-prompted AI edit ("Speak" button: hold to record, release to send)
    # ------------------------------------------------------------

    def get_custard_cream_client(self):
        if self.custard_cream_client is None:
            self.custard_cream_client = CustardCreamClient(
                api_key_env=self.custard_cream_settings.get("api_key_env", "GOOGLE_API_KEY"),
                transcribe_model=self.custard_cream_settings.get("transcribe_model", "gemini-2.5-flash"),
                edit_model=self.custard_cream_settings.get("edit_model", "gemini-2.5-flash-image"),
                timeout_seconds=self.custard_cream_settings.get("timeout_seconds", 30),
            )
        return self.custard_cream_client

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

    def status_frame(self, text):
        """A short status banner over the current backdrop. Word-wraps to as many lines as
        needed - most callers pass a short fixed string that always fits on one line (unchanged
        from before), but a transcribed voice prompt can run to a full sentence.
        """
        if self.mode in ("play", "play_grid") and self.play_view is not None:
            base = self.play_view
        elif self.finder is not None:
            base = self.finder
        else:
            base = Image.new("RGB", (480, 320), (0, 0, 0))
        frame = base.copy()
        draw = ImageDraw.Draw(frame)

        max_width = frame.width - 20
        words = text.split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=self.medium_font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            lines = [text]

        line_height = 40
        block_height = line_height * len(lines) + 10
        top = frame.height // 2 - block_height // 2
        draw.rectangle((0, top, frame.width, top + block_height), fill=(0, 0, 0))
        for i, line in enumerate(lines):
            y = top + 10 + i * line_height + line_height // 2
            draw.text((frame.width // 2, y), line, font=self.medium_font, fill=(255, 255, 255), anchor="mm")
        return frame

    def qr_result_frame(self, url, phrase):
        """Shown after a successful publish to custard-cream-server: a QR code linking to the
        picture's page, plus the three-word phrase as a human-readable fallback for anyone who
        can't scan it.
        """
        frame = Image.new("RGB", (480, 320), (0, 0, 0))
        draw = ImageDraw.Draw(frame)

        qr_size = 200
        url = url.replace(":3001","")
        qr_img = qrcode.make(url).convert("RGB").resize((qr_size, qr_size))
        qr_x = 20
        frame.paste(qr_img, (qr_x, frame.height // 2 - qr_size // 2))

        text_x = qr_x + qr_size + 10
        draw.text((text_x, frame.height // 2 - 30), "Published!", font=self.medium_font, fill=(255, 255, 255))
        draw.text((text_x, frame.height // 2 + 10), phrase, font=self.phrase_font, fill=(255, 255, 0))

        return frame

    def show_result(self, img, hold_seconds):
        """Draws img and holds it on screen for a while, staying responsive to window-close."""
        self.screen.draw(img)
        end_time = time.time() + hold_seconds
        while self.running and not self.screen.quit_requested and time.time() < end_time:
            self.screen.update()
            time.sleep(0.05)

    def show_result_until_done(self, img):
        """Like show_result(), but stays up until a "Done" button is pressed instead of a fixed
        delay - used for the publish QR code/phrase screen, since there's no telling how long
        someone needs to get their phone out and scan it."""
        done_pressed = Event()
        button_y = self.screen.HEIGHT - 50
        done_button = Button(self.screen.WIDTH - 110, button_y, 110, 50, "Done", self.play_button_font,
                              (255, 255, 255), (90, 90, 90), None, done_pressed.set)

        self.screen.set_buttons((done_button,))
        self.screen.draw(img)
        while self.running and not self.screen.quit_requested and not done_pressed.is_set():
            self.screen.update()
            time.sleep(0.05)

    def start_voice_prompt(self):
        if self.ai_pending or self.print_pending:
            return
        try:
            self.transcriber.start(on_partial=self._on_voice_partial)
        except Exception as e:
            print(f"Could not start recording: {e}")
            self.show_result(self.status_frame("Mic error"), hold_seconds=2)
            if self.mode == "play":
                self.show_play_image()
            return
        print("Speak: recording started")
        self.voice_recording = True
        self.voice_partial_text = None
        self.screen.draw(self.status_frame("Recording... release to send"))

    def _on_voice_partial(self, text):
        """Called from the transcriber's background thread as live partial results arrive."""
        self.voice_partial_text = text
        self.voice_partial_ready.set()

    def finish_voice_prompt(self, image_path=None):
        """image_path: use this existing photo (from Play mode) instead of capturing a fresh one."""
        self.voice_recording = False
        if self.ai_pending:
            self.transcriber.stop()
            return

        has_audio = self.transcriber.stop()
        if not has_audio:
            print("Speak: no audio captured")
            self.show_result(self.status_frame("No audio captured"), hold_seconds=2)
            if self.mode == "play":
                self.show_play_image()
            return

        if image_path is None:
            still_path = self.save_dir / "ai_source.jpg"
            self.picam2.switch_mode_and_capture_file(self.still_config, str(still_path))
            print(f"Speak: captured fresh photo {still_path}")
        else:
            still_path = image_path
            print(f"Speak: using existing photo {still_path}")

        self.ai_pending = True
        self.ai_prompt_text = None
        self.ai_done.clear()
        Thread(target=self.run_ai_edit, args=(still_path,), daemon=True).start()

    def run_ai_edit(self, still_path):
        """Runs on a background thread so the viewfinder/buttons stay responsive while waiting on the network."""
        try:
            prompt_text = self.transcriber.finalize()
            if not prompt_text:
                self.ai_result = ("status", "Didn't catch that")
            else:
                self.ai_prompt_text = prompt_text
                self.ai_prompt_ready.set()
                client = self.get_custard_cream_client()
                edited_bytes = client.edit_image(still_path.read_bytes(), prompt_text)
                if edited_bytes is None:
                    self.ai_result = ("status", "No image returned")
                else:
                    self.ai_result = ("image", edited_bytes, prompt_text)
        except Exception as e:
            print(f"Speak: AI edit failed: {e}")
            self.ai_result = ("status", "AI edit failed")
        finally:
            self.ai_done.set()

    def finish_ai_edit(self):
        self.ai_pending = False
        result = self.ai_result
        self.ai_result = None
        self.ai_prompt_text = None
        self.ai_done.clear()
        came_from_play = self.mode == "play"

        try:
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
            self.ai_prompts_by_path[out_path] = prompt_text
            print(f"Saved {out_path} (prompt: {prompt_text!r})")

            result_img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((480, 320))
            self.show_result(result_img, hold_seconds=self.custard_cream_settings.get("result_hold_seconds", 4))

            if came_from_play:
                # The new edit becomes the current selection, same as if it had just been taken.
                self.play_images.insert(0, out_path)
                self.play_index = 0
        finally:
            # Only if this edit was triggered from Play mode - the remote's direct hold-to-talk
            # never touches Play mode, so this is a no-op for that path.
            if came_from_play:
                self.show_play_image()

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
            self.last_metadata = request.get_metadata()
            request.release()

            self.finder = Image.fromarray(frame, "RGB")

            if self.mode == "capture":
                dirty = True

            self.request_next_frame()

        if self.screen.update():
            dirty = True

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

        if self.voice_partial_ready.is_set():
            self.voice_partial_ready.clear()
            dirty = True

        if self.ai_prompt_ready.is_set():
            self.ai_prompt_ready.clear()
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
                self.screen.draw(self.status_frame(self.ai_prompt_text or "Processing..."))
            elif self.publish_pending:
                self.screen.draw(self.status_frame("Publishing..."))
            elif self.print_pending:
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
                    elif key == " ":
                        # Same "switch to Capture rather than shoot blind" rule as the physical
                        # shutter remote - see the equivalent branch in process_frame().
                        if self.mode in ("play", "play_grid"):
                            self.enter_capture()
                        else:
                            self.save_image()

        except KeyboardInterrupt:
            pass
        finally:
            print("System stopping: tidying up")
            if self.shutter_remote is not None:
                self.shutter_remote.stop()
            if self.serial_remote is not None:
                self.serial_remote.stop()
            self.screen.close()
            self.kbd.close()
            self.picam2.stop()


def main():
    custard_cream_camera = CustardCreamCamera()
    custard_cream_camera.run()


if __name__ == "__main__":
    main()
