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

from libcamera import Transform
from PIL import Image, ImageDraw, ImageFont
from picamera2 import Picamera2

from displays import Button, create_display
from custard_cream import AudioRecorder, CustardCreamClient
from print_overlays import apply_datestamp, apply_watermark
from publishers import create_publisher
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

        # Speak/Print/Publish all open the image browser rather than acting immediately - see
        # enter_browse(). There's no on-screen quit button any more - use keyboard 'q', or
        # Escape/window-close on the HDMI backends.
        self.main_menu = (
            Button(0, button_y, 110, 50, "Click", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.save_image),
            Button(123, button_y, 110, 50, "Speak", self.medium_font, (255, 255, 255), (0, 110, 0), None, lambda: self.enter_browse("speak")),
            Button(246, button_y, 110, 50, "Print", self.medium_font, (255, 255, 255), (90, 90, 90), None, lambda: self.enter_browse("print")),
            Button(369, button_y, 110, 50, "Publish", self.medium_font, (255, 255, 255), (150, 90, 0), None, lambda: self.enter_browse("publish")),
            # Exposure compensation - tucked into the top corners since the bottom row is full.
            Button(0, 0, 50, 40, "EV-", self.small_font, (255, 255, 255), (60, 60, 60), None, lambda: self.adjust_exposure(-self.ev_step)),
            Button(430, 0, 50, 40, "EV+", self.small_font, (255, 255, 255), (60, 60, 60), None, lambda: self.adjust_exposure(self.ev_step)),
        )

        self.screen.set_buttons(self.main_menu)

        self.save_dir = Path("captures")
        self.save_dir.mkdir(exist_ok=True)

        printing_settings = settings.get("printing", {})
        self.printer_name = printing_settings.get("printer")
        self.print_test_mode = printing_settings.get("test_mode", False)
        self.print_test_dir = Path(printing_settings.get("test_folder", "print_tests"))
        if self.print_test_mode:
            self.print_test_dir.mkdir(exist_ok=True)

        self.watermark_settings = settings.get("watermark", {})
        self.datestamp_settings = settings.get("datestamp", {})

        self.finder = None
        self.last_metadata = None
        self.img = None
        self.running = None
        self.save_file_name = None
        self.last_photo_path = None

        # Image browser ("Speak"/"Print" buttons): mode is one of "live", "browse_grid",
        # "browse_preview". browse_view holds whatever the current grid/preview frame is, drawn
        # in place of the live viewfinder while mode != "live".
        self.mode = "live"
        self.browse_pending_action = None
        self.browse_images = []
        self.browse_page = 0
        self.browse_selected_path = None
        self.browse_view = None

        # Voice-prompted AI edit ("Speak" button)
        custard_cream_settings = settings.get("custard_cream", {})
        self.custard_cream_settings = custard_cream_settings
        self.audio_recorder = AudioRecorder(
            sample_rate=custard_cream_settings.get("sample_rate", 16000),
            channels=custard_cream_settings.get("channels", 1),
            max_seconds=custard_cream_settings.get("max_record_seconds", 15),
            device=custard_cream_settings.get("device"),
        )
        self.audio_path = Path(tempfile.gettempdir()) / "magic_camera_prompt.wav"
        self.custard_cream_client = None
        self.ai_pending = False
        self.ai_done = Event()
        self.ai_result = None

        # Publishing ("Publish" button) - pluggable, see publishers/. Lazily created since it
        # needs API credentials that may not be configured if the feature isn't used, and runs
        # on a background thread the same way the AI edit does, for the same reason (network I/O
        # shouldn't block the viewfinder/buttons).
        self.publisher = None
        self.publish_pending = False
        self.publish_done = Event()
        self.publish_result = None

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
        """Best-effort audio playback via `aplay` - fires and forgets rather than waiting for
        the sound to finish, and never raises: a missing/misconfigured audio device (or no
        audio hardware at all) should mean silence, not a broken shutter button.
        """
        if not self.audio_output_settings.get("enabled", True):
            return

        args = ["aplay", "-q"]
        device = self.audio_output_settings.get("device")
        if device:
            args += ["-D", device]
        args.append(str(path))

        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            print(f"Could not play sound {path}: {e}")

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

        out_path = Path(tempfile.gettempdir()) / "magic_camera_print.jpg"
        img.save(out_path, "JPEG", quality=95)
        return out_path

    def print_image(self, path=None):
        path = path or self.last_photo_path
        if path is None:
            print("Nothing to print yet")
            self.show_result(self.status_frame("Nothing to print yet"), hold_seconds=2)
            return

        print_path = self.prepare_print_copy(path)

        if self.print_test_mode:
            # Exercises the full pipeline (watermark/date stamp included) without spending
            # paper/ink - saves what would have been sent to `lp` instead of actually sending it.
            ts = time.strftime("%Y%m%d_%H%M%S")
            test_path = self.print_test_dir / f"print_test_{ts}.jpg"
            shutil.copyfile(print_path, test_path)
            print(f"Print testing: saved {test_path} instead of printing")
            self.show_result(self.status_frame("Test print saved"), hold_seconds=2)
            return

        print(f"Printing {path}" + (f" (with overlays: {print_path})" if print_path != path else ""))
        self.show_result(self.status_frame("Printing..."), hold_seconds=1)

        cmd = ["lp"]
        if self.printer_name:
            cmd += ["-d", self.printer_name]
        cmd.append(str(print_path))

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
    # Image browser ("Speak"/"Print" open this to pick which photo to act on)
    # ------------------------------------------------------------

    def enter_browse(self, action):
        if self.ai_pending or self.publish_pending:
            return
        self.browse_pending_action = action
        self.browse_page = 0
        self.browse_images = sorted(
            (p for p in self.save_dir.glob("*.jpg") if p.name != "ai_source.jpg"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        self.show_browse_grid()

    def exit_browse(self):
        self.mode = "live"
        self.browse_pending_action = None
        self.browse_selected_path = None
        self.browse_images = []
        self.screen.set_buttons(self.main_menu)
        if self.finder is not None:
            self.screen.draw(self.finder)

    def show_browse_grid(self):
        self.mode = "browse_grid"
        button_y = self.screen.HEIGHT - 50

        if not self.browse_images:
            self.screen.set_buttons((
                Button(330, button_y, 150, 50, "Quit", self.medium_font, (255, 255, 255), (150, 0, 0), None, self.exit_browse),
            ))
            self.browse_view = self.status_frame("No photos yet")
            self.screen.draw(self.browse_view)
            return

        self.screen.set_buttons(())
        self.screen.draw(self.status_frame("Loading..."))

        cols, rows = 3, 3
        per_page = cols * rows
        grid_height = button_y
        cell_w = self.screen.WIDTH // cols
        cell_h = grid_height // rows

        page_start = self.browse_page * per_page
        page_images = self.browse_images[page_start:page_start + per_page]

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

            thumb_buttons.append(Button(
                cell_x, cell_y, cell_w, cell_h, "", self.small_font, (0, 0, 0), (0, 0, 0),
                up_handler=None, down_handler=(lambda p=path: self.show_browse_preview(p)), visible=False,
            ))

        self.browse_view = canvas

        nav_buttons = (
            Button(0, button_y, 150, 50, "Left", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.browse_prev_page),
            Button(165, button_y, 150, 50, "Right", self.medium_font, (255, 255, 255), (0, 0, 0), None, self.browse_next_page),
            Button(330, button_y, 150, 50, "Quit", self.medium_font, (255, 255, 255), (150, 0, 0), None, self.exit_browse),
        )
        self.screen.set_buttons((*nav_buttons, *thumb_buttons))
        self.screen.draw(self.browse_view)

    def browse_prev_page(self):
        if self.browse_page > 0:
            self.browse_page -= 1
            self.show_browse_grid()

    def browse_next_page(self):
        max_page = (len(self.browse_images) - 1) // 9
        if self.browse_page < max_page:
            self.browse_page += 1
            self.show_browse_grid()

    def show_browse_preview(self, path):
        self.mode = "browse_preview"
        self.browse_selected_path = path

        try:
            self.browse_view = Image.open(path).convert("RGB").resize((self.screen.WIDTH, self.screen.HEIGHT))
        except Exception as e:
            print(f"Could not load {path}: {e}")
            self.show_browse_grid()
            return

        button_y = self.screen.HEIGHT - 50
        if self.browse_pending_action == "speak":
            # Hold-to-talk, same as the original Speak button, just targeting this chosen image.
            select_btn = Button(
                0, button_y, 230, 50, "Select", self.medium_font, (255, 255, 255), (0, 110, 0),
                up_handler=self.finish_selected_voice_prompt, down_handler=self.start_voice_prompt,
            )
        elif self.browse_pending_action == "publish":
            select_btn = Button(
                0, button_y, 230, 50, "Select", self.medium_font, (255, 255, 255), (0, 110, 0),
                up_handler=None, down_handler=self.select_browse_publish,
            )
        else:
            select_btn = Button(
                0, button_y, 230, 50, "Select", self.medium_font, (255, 255, 255), (0, 110, 0),
                up_handler=None, down_handler=self.select_browse_print,
            )
        ignore_btn = Button(
            250, button_y, 230, 50, "Ignore", self.medium_font, (255, 255, 255), (90, 90, 90),
            up_handler=None, down_handler=self.show_browse_grid,
        )

        self.screen.set_buttons((select_btn, ignore_btn))
        self.screen.draw(self.browse_view)

    def select_browse_print(self):
        self.print_image(self.browse_selected_path)
        self.exit_browse()

    def finish_selected_voice_prompt(self):
        self.finish_voice_prompt(image_path=self.browse_selected_path)

    # ------------------------------------------------------------
    # Publishing ("Publish" button, via the image browser)
    # ------------------------------------------------------------

    def get_publisher(self):
        if self.publisher is None:
            self.publisher = create_publisher(self.settings)
        return self.publisher

    def select_browse_publish(self):
        self.publish_pending = True
        self.publish_done.clear()
        Thread(target=self.run_publish, args=(self.browse_selected_path,), daemon=True).start()

    def run_publish(self, image_path):
        """Runs on a background thread so the viewfinder/buttons stay responsive while waiting on the network."""
        try:
            publisher = self.get_publisher()
            ok = publisher.publish(image_path)
            self.publish_result = "Published!" if ok else "Publish failed"
        except Exception as e:
            print(f"Publish failed: {e}")
            self.publish_result = "Publish failed"
        finally:
            self.publish_done.set()

    def finish_publish(self):
        self.publish_pending = False
        message = self.publish_result
        self.publish_result = None
        self.publish_done.clear()
        self.show_result(self.status_frame(message), hold_seconds=2)
        self.exit_browse()

    # ------------------------------------------------------------
    # Voice-prompted AI edit ("Speak" button: hold to record, release to send)
    # ------------------------------------------------------------

    def get_custard_cream_client(self):
        if self.custard_cream_client is None:
            self.custard_cream_client = CustardCreamClient(
                api_key_env=self.custard_cream_settings.get("api_key_env", "GOOGLE_API_KEY"),
                transcribe_model=self.custard_cream_settings.get("transcribe_model", "gemini-2.5-flash"),
                edit_model=self.custard_cream_settings.get("edit_model", "gemini-2.5-flash-image"),
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
        base = self.finder if self.finder is not None else Image.new("RGB", (480, 320), (0, 0, 0))
        frame = base.copy()
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, frame.height // 2 - 25, frame.width, frame.height // 2 + 25), fill=(0, 0, 0))
        draw.text((frame.width // 2, frame.height // 2), text, font=self.medium_font, fill=(255, 255, 255), anchor="mm")
        return frame

    def show_result(self, img, hold_seconds):
        """Draws img and holds it on screen for a while, staying responsive to window-close."""
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
            if self.browse_pending_action == "speak":
                self.exit_browse()
            return
        self.screen.draw(self.status_frame("Recording... release to send"))

    def finish_voice_prompt(self, image_path=None):
        """image_path: use this existing photo (from the browser) instead of capturing a fresh one."""
        if self.ai_pending:
            self.audio_recorder.stop()
            return

        audio_path = self.audio_recorder.stop()
        if audio_path is None:
            self.show_result(self.status_frame("No audio captured"), hold_seconds=2)
            if self.browse_pending_action == "speak":
                self.exit_browse()
            return

        if image_path is None:
            still_path = self.save_dir / "ai_source.jpg"
            self.picam2.switch_mode_and_capture_file(self.still_config, str(still_path))
        else:
            still_path = image_path

        self.ai_pending = True
        self.ai_done.clear()
        Thread(target=self.run_ai_edit, args=(audio_path, still_path), daemon=True).start()

    def run_ai_edit(self, audio_path, still_path):
        """Runs on a background thread so the viewfinder/buttons stay responsive while waiting on the network."""
        try:
            client = self.get_custard_cream_client()
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
        came_from_browse = self.browse_pending_action == "speak"

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
            print(f"Saved {out_path} (prompt: {prompt_text!r})")

            result_img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((480, 320))
            self.show_result(result_img, hold_seconds=self.custard_cream_settings.get("result_hold_seconds", 4))
        finally:
            # Only if this edit was triggered via the image browser's "Select" - the remote's
            # direct hold-to-talk never enters browse mode, so this is a no-op for that path.
            if came_from_browse:
                self.exit_browse()

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

            if self.mode == "live":
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

        if self.publish_pending and self.publish_done.is_set():
            self.finish_publish()
            dirty = True

        if dirty:
            if self.ai_pending:
                self.screen.draw(self.status_frame("Processing..."))
            elif self.publish_pending:
                self.screen.draw(self.status_frame("Publishing..."))
            elif self.mode in ("browse_grid", "browse_preview"):
                self.screen.draw(self.browse_view)
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
