import io
import json
import queue
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
from PIL import Image, ImageDraw, ImageFont, ImageOps

# displays/publishers/transcription packages and NanoBananaClient.py/print_overlays.py/
# ftp_server.py all live in ./lib, next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from displays import Button, colours, create_display
from NanoBananaClient import CustardCreamClient
from print_overlays import apply_datestamp, apply_watermark
from publishers import available_publishers, create_publisher, publisher_label
from transcription import create_transcriber

SETTINGS_PATH = Path(__file__).parent / "settings.json"
VERSION_PATH = Path(__file__).parent / "VERSION"
GITHUB_URL = "https://github.com/CrazyRobMiles/custard-cream-camera"

# IPP job-state values (RFC 8011 SS5.3.7) - pycups surfaces the raw int rather than named
# constants, so the ones this code checks for are spelled out here instead.
CUPS_JOB_STATE_CANCELED = 7
CUPS_JOB_STATE_ABORTED = 8
CUPS_JOB_STATE_COMPLETED = 9

# How often wait_for_print_job() refreshes the on-screen status from `lpstat -t` while a print
# is in flight - frequent enough to catch a paper-out/jam message promptly, without spawning a
# subprocess on every 1s job-state poll.
LPSTAT_POLL_SECONDS = 5


def load_settings():
    with open(SETTINGS_PATH) as f:
        return json.load(f)


def load_version():
    try:
        return VERSION_PATH.read_text().strip()
    except OSError:
        return "unknown"


def _largest_size_with_aspect(max_width, max_height, aspect):
    """The largest (width, height) with the given width/height aspect ratio that fits within
    max_width x max_height, rounded down to even dimensions (some capture formats require it).
    Used to size both the still capture and the live preview from the printed aspect ratio
    (settings["printing"]) rather than the sensor's native aspect or the screen's own aspect, so
    the framing seen live always matches what actually gets printed - see self.print_aspect.
    """
    if max_width / max_height > aspect:
        height = max_height
        width = height * aspect
    else:
        width = max_width
        height = width / aspect
    return int(width) // 2 * 2, int(height) // 2 * 2


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


class CustardCreamCamera:
    """Home screen(s) picked by settings.json's "mode":

    - "camera" (self.has_camera=True, self.has_ftp=False): a live Picamera2 viewfinder with
      Capture/Play modes.
    - "ftp" (self.has_camera=False, self.has_ftp=True): no camera - photos arrive over FTP (see
      lib/ftp_server.py) and the app is always in Play/play_grid, starting on a "waiting for
      photos" placeholder.
    - "camera_ftp" (both True): a live Picamera2 viewfinder like camera mode, plus the FTP
      receiver running in the background - an FTP upload interrupts Capture/Play the same way it
      does in "ftp" mode, landing back in Capture mode is unaffected.

    Either way, reviewing/printing/publishing/voice-editing photos already in save_dir - the
    "review station" methods below (Play mode, printing, publishing, the voice/keyboard AI-edit
    flow) - is exactly the same regardless of mode; only the few methods under "Camera-mode hooks"
    branch on self.has_camera, and the FTP receiver's own setup/polling/teardown branch on
    self.has_ftp.
    """

    # Button colour per destination, shown in the publish menu - falls back to grey for any
    # publisher type not listed here.
    PUBLISH_MENU_COLOURS = {
        "flickr": colours.PUBLISH,
        "bsky": colours.BSKY,
        "custard_cream_server": colours.CUSTARD_CREAM_SERVER,
    }

    def __init__(self):
        settings = load_settings()
        self.settings = settings
        self.app_dir = Path(__file__).resolve().parent
        self.version = load_version()
        mode_setting = settings.get("mode", "camera")
        self.has_camera = mode_setting in ("camera", "camera_ftp")
        self.has_ftp = mode_setting in ("ftp", "camera_ftp")

        # Read early - both the still and live-preview capture sizes below are derived from this
        # (not the sensor's native aspect, not the screen's own aspect), so what's framed live
        # always matches what actually comes out of the printer. Paper size is configurable
        # rather than assuming this printer's 6x4in postcard size forever.
        printing_settings = settings.get("printing", {})
        self.printing_settings = printing_settings
        self.print_aspect = (
            printing_settings.get("paper_width_inches", 6) / printing_settings.get("paper_height_inches", 4)
        )

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

        # AI-edit input: "voice" (hold-to-talk + a transcriber) or "keyboard" (tap, pick a preset
        # prompt or type a custom one) - or disabled entirely. Read early since it decides what
        # the play menu's Speak/AI Edit button looks like (_build_play_menu() below) and whether
        # a transcriber is created at all further down.
        ai_edit_settings = settings.get("ai_edit", {})
        self.ai_edit_settings = ai_edit_settings
        self.ai_edit_enabled = ai_edit_settings.get("enabled", True)
        self.ai_input_method = ai_edit_settings.get("input_method", "voice")

        self.kbd = Keyboard()

        button_y = self.screen.HEIGHT - 50
        arrow_y = 40 + (self.screen.HEIGHT - 40 - 50 - 100) // 2
        # Height of the area actually visible above the bottom Capture/Play button row - the
        # live preview is fit within this area (see preview_config below) rather than the full
        # screen height, so it's never drawn full-screen only to have its bottom strip hidden
        # behind the opaque button bar.
        self.content_height = button_y

        if self.has_camera:
            # picamera2/libcamera and the shutter-remote modules are only importable on a device
            # with the Pi camera stack/hardware actually installed - never attempted in FTP mode.
            from libcamera import Transform
            from picamera2 import Picamera2
            from gpio_shutter_remote import GpioShutterRemote
            from serial_shutter_remote import SerialShutterRemote
            from shutter_remote import ShutterRemote

            self.picam2 = Picamera2()

            # Corrects for the sensor being mounted rotated 180 degrees in this build - flip both
            # axes rather than rotating every captured frame in software afterward. Viewfinder and
            # capture are transformed independently (each falling back to the top-level hflip/vflip
            # when not overridden) so a traditional reflex-style viewfinder - e.g. mirrored left-
            # right relative to what's actually saved - can be set up without affecting stills.
            camera_settings = settings.get("camera", {})
            base_hflip = camera_settings.get("hflip", False)
            base_vflip = camera_settings.get("vflip", False)
            viewfinder_settings = camera_settings.get("viewfinder", {})
            capture_settings = camera_settings.get("capture", {})

            # Auto-switch to Play mode after Capture mode sits idle for a while - Capture mode
            # keeps the sensor streaming continuously (see enter_play()/enter_capture() below),
            # which is the expensive state to be left in unattended. Off by default since it
            # changes on-screen behavior, not just performance.
            idle_timeout_settings = camera_settings.get("idle_timeout", {})
            self.idle_timeout_enabled = idle_timeout_settings.get("enabled", False)
            self.idle_timeout_seconds = idle_timeout_settings.get("seconds", 60)
            self.last_capture_activity = time.monotonic()
            viewfinder_transform = Transform(
                hflip=viewfinder_settings.get("hflip", base_hflip),
                vflip=viewfinder_settings.get("vflip", base_vflip),
            )
            capture_transform = Transform(
                hflip=capture_settings.get("hflip", base_hflip),
                vflip=capture_settings.get("vflip", base_vflip),
            )

            # An explicit optical crop to self.print_aspect, centered in the sensor's full pixel
            # array - deliberately not just requesting an output "size" of that aspect ratio and
            # trusting the ISP to crop for us: without ScalerCrop, a main-stream size narrower
            # than the sensor mode's own aspect ratio gets the whole field of view non-uniformly
            # squeezed to fit instead of cropped, distorting the image (visible on stills; the
            # live preview only "looked fine" because the same squeeze is subtler on a small,
            # moving image). Reading sensor_resolution rather than hardcoding it also means this
            # keeps working if the camera module itself changes, not just the printer.
            sensor_w, sensor_h = self.picam2.sensor_resolution
            crop_w, crop_h = _largest_size_with_aspect(sensor_w, sensor_h, self.print_aspect)
            self.print_crop = ((sensor_w - crop_w) // 2, (sensor_h - crop_h) // 2, crop_w, crop_h)

            # Left to its own defaults, Picamera2 picks whichever sensor mode can supply the
            # requested preview main-stream size - for a small preview resolution that's often a
            # genuinely cropped/windowed readout mode, not a full-field-of-view binned one,
            # narrowing the preview's field of view relative to stills (which always use the
            # full-resolution, and therefore full-FOV, mode). That mismatch shows up as the live
            # viewfinder looking "zoomed in" next to what's actually printed. Pinning the preview
            # to the smallest mode that still covers the full sensor FOV keeps the two in sync -
            # still preview-sized, just not cropped. crop_limits gives each mode's available crop
            # rectangle in native sensor coordinates, so the mode(s) tied for the largest one are
            # exactly the full-FOV modes.
            sensor_modes = self.picam2.sensor_modes
            max_fov_area = max(m["crop_limits"][2] * m["crop_limits"][3] for m in sensor_modes)
            full_fov_modes = [m for m in sensor_modes if m["crop_limits"][2] * m["crop_limits"][3] == max_fov_area]
            preview_sensor_mode = min(full_fov_modes, key=lambda m: m["size"][0] * m["size"][1])

            # Both capture sizes are fit within the largest box available - the full crop for
            # stills, the on-screen content area for the live preview - and since the crop is
            # already at print_aspect, the ISP's scale down to either output size is always
            # uniform. _place_in_frame() handles centering/letterboxing either one on screen.
            # Capping the preview frame rate matters on low-powered hardware: each frame drives
            # a full copy/overlay/letterbox/encode/Tk-swap in process_frame(), and left uncapped
            # this runs at the sensor mode's native rate (often 30-60fps+) - far faster than the
            # on-screen viewfinder needs, and enough to starve Tkinter's event loop of time to
            # process touch input, which is what makes buttons feel laggy/unresponsive. Setting
            # it to None disables the cap. Trade-off: this also caps the longest exposure time
            # AE/EV+ can reach (frame duration must be >= exposure time), so a very low preview_fps
            # could clip EV+ headroom in dim scenes - 15fps leaves ~66ms, well above typical
            # metered exposure times indoors/outdoors.
            preview_controls = {}
            preview_fps = camera_settings.get("preview_fps", 15)
            if preview_fps:
                frame_duration_us = int(1_000_000 / preview_fps)
                preview_controls["FrameDurationLimits"] = (frame_duration_us, frame_duration_us)

            self.preview_config = self.picam2.create_preview_configuration(
                main={"size": _largest_size_with_aspect(self.screen.WIDTH, self.content_height, self.print_aspect), "format": "BGR888"},
                transform=viewfinder_transform,
                controls=preview_controls,
                sensor={"output_size": preview_sensor_mode["size"], "bit_depth": preview_sensor_mode["bit_depth"]},
            )

            self.still_config = self.picam2.create_still_configuration(
                main={"size": (crop_w, crop_h), "format": "BGR888"},
                transform=capture_transform,
                controls={"ScalerCrop": self.print_crop},
            )

            self.picam2.configure(self.preview_config)

            # print_crop's coordinates were computed against sensor_resolution, the full-FOV
            # mode picked above should honour them unclamped - but re-deriving the crop from
            # this mode's own bounds (queryable only now, after configure(), once the mode is
            # actually active) rather than assuming they match sensor_resolution exactly is a
            # cheap belt-and-braces: if the two ever disagree, libcamera would otherwise silently
            # clamp print_crop to whatever's valid, which can leave it at something other than
            # print_aspect - and the ISP would then stretch that wrong-aspect crop to fill the
            # still-print_aspect main stream size, distorting the live preview specifically (this
            # is what previously showed up as the viewfinder looking vertically stretched while
            # Play-mode/printed photos looked right).
            _, preview_crop_bounds, _ = self.picam2.camera_controls["ScalerCrop"]
            mode_x, mode_y, mode_w, mode_h = preview_crop_bounds
            preview_crop_w, preview_crop_h = _largest_size_with_aspect(mode_w, mode_h, self.print_aspect)
            preview_crop = (
                mode_x + (mode_w - preview_crop_w) // 2,
                mode_y + (mode_h - preview_crop_h) // 2,
                preview_crop_w,
                preview_crop_h,
            )
            self.picam2.set_controls({"ScalerCrop": preview_crop})

            self.picam2.start()
            # Tracks whether the sensor is actually streaming - Play mode stops it (see
            # enter_play() below), since the live feed is never shown there, and this is what
            # enter_capture()/process_frame() check to know whether to restart it and resume
            # pumping capture_request()s.
            self.camera_streaming = True

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

            comp_button_width = 80
            comp_button_height = 80

            # Capture mode: live viewfinder, take a photo or switch to Play mode to review/act on
            # existing ones. There's no on-screen quit button any more - use keyboard 'q', or
            # Escape/window-close on the  MI backends.
            self.capture_menu = (
                *self._row_of_buttons(button_y, 50, (
                    ("Click", self.medium_font, colours.BUTTON_TEXT, colours.PRIMARY, None, self.save_image),
                    ("Play", self.medium_font, colours.BUTTON_TEXT, colours.PLAY, None, self.enter_play),
                )),
                # Exposure compensation - tucked into the top corners since the bottom row is full.
                Button(0, 0, comp_button_width, comp_button_height, "EV-", self.small_font, colours.BUTTON_TEXT, colours.UTILITY, None, lambda: self.adjust_exposure(-self.ev_step)),
                Button(self.screen.WIDTH - comp_button_width, 0, comp_button_width, comp_button_height, "EV+", self.small_font, colours.BUTTON_TEXT, colours.UTILITY, None, lambda: self.adjust_exposure(self.ev_step)),
            )

            self.screen.set_buttons(self.capture_menu)

        # Play mode: reviews/acts on captures/ directly - Print/Speak or AI Edit/Publish always
        # target whatever's currently selected (self.play_index), no separate "choose, then act"
        # step. Left/Right step through images one at a time; Page opens a 3x3 grid to jump
        # further. Built regardless of mode - _build_play_menu() itself only adds a "Capture"
        # button when self.has_camera is set, so a camera-less "ftp" mode gets none.
        self.play_menu = self._build_play_menu(button_y, arrow_y)

        self.save_dir = Path("captures")
        self.save_dir.mkdir(exist_ok=True)

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
        # Last (path, placed-and-letterboxed image) decoded by show_play_image() - every "Back"
        # button in the app (grid/publish-menu/AI-picker) returns here without changing
        # play_index, so without this show_play_image() would re-decode and re-resize the same
        # full-resolution photo from disk on every single Back tap. Files in save_dir are never
        # modified in place once written (edits/new captures always get a new path), so caching
        # by path alone is safe - no mtime check needed.
        self._play_view_cache_path = None
        self._play_view_cache_img = None
        # Maps a saved ai_<timestamp>.jpg Path to the voice instruction that produced it, so
        # Publish can send it along as the picture's aiInstruction (see finish_ai_edit()/
        # run_publish()). Only populated for the current session - edits from a previous run
        # have no entry, which is fine, since the text was never persisted anywhere else either.
        self.ai_prompts_by_path = {}

        # Voice-prompted AI edit ("Speak" button)
        custard_cream_settings = settings.get("custard_cream", {})
        self.custard_cream_settings = custard_cream_settings
        self.custard_cream_client = None
        # Only created for the "voice" input method - create_transcriber() (see
        # lib/transcription/__init__.py) imports and eagerly loads a local Vosk model when
        # "transcribe_provider" is "vosk", a real cost not worth paying on a device that never
        # uses voice input at all (e.g. a low-spec keyboard/preset-only image receiver).
        self.transcriber = None
        if self.ai_edit_enabled and self.ai_input_method == "voice":
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

        # "AI Edit" button (ai_edit.input_method == "keyboard") - the picker screen's own button
        # handlers only set these (see show_ai_prompt_picker() below) rather than entering the
        # blocking confirm/edit screens directly, since those handlers run from inside
        # ButtonPanel.update()/self.screen.update() - process_frame() picks the choice up on a
        # later tick instead, the same pattern ai_transcribe_done/ai_done use below.
        self.ai_prompt_choice_text = None
        self.ai_prompt_choice_is_custom = False
        self.ai_prompt_choice_ready = Event()

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
            # Shutter remotes - Bluetooth, wired USB-serial and/or a physical GPIO button, any or
            # all of which can be enabled at once (see settings.json's "shutter_remote"/
            # "serial_remote"/"gpio_remote" blocks). The Bluetooth remote's physical button sends a
            # real press+release, so its "speak" key drives hold-to-talk the same way the on-screen
            # Speak button does; the serial and GPIO remotes only ever send a single-shot "click",
            # so they're wired to remote_photo_requested only, the same event the Bluetooth remote's
            # photo_key sets. All the Events below are set from a remote's background listener
            # thread (or, for the GPIO remote, gpiozero's own interrupt handler) and only ever acted
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
                # Only wired for the "voice" input method - it drives hold-to-talk, which is
                # meaningless (and self.transcriber is None) for "keyboard" or a disabled ai_edit.
                if speak_key and self.ai_edit_enabled and self.ai_input_method == "voice":
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

            gpio_remote_settings = settings.get("gpio_remote", {})
            self.gpio_remote = None
            if gpio_remote_settings.get("enabled", False):
                self.gpio_remote = GpioShutterRemote(
                    pin=gpio_remote_settings.get("pin", 26),
                    on_click=self.remote_photo_requested.set,
                    active_low=gpio_remote_settings.get("active_low", True),
                )
                self.gpio_remote.start()

        if self.has_ftp:
            from ftp_server import FTPReceiver

            # FTP receiver - runs on its own background thread; on_file_received() (see
            # lib/ftp_server.py) flattens each completed upload into save_dir and queues its Path
            # here for process_frame() to pick up on the main thread.
            self.incoming_queue = queue.Queue()
            self.ftp_receiver = FTPReceiver(settings.get("ftp", {}), self.save_dir, self.incoming_queue)
            self.ftp_receiver.start()

        if not self.has_camera:
            # Camera-less "ftp" mode has no Capture mode to start in - picks up anything already
            # in save_dir (e.g. left over from a previous run) and shows the newest, or the
            # "waiting for photos" placeholder if there's nothing yet. "camera_ftp" mode starts in
            # Capture mode instead (self.mode below), same as plain "camera" mode.
            self.enter_play()

    def _build_play_menu(self, button_y, arrow_y):
        """Play mode's button row plus the Stop/Page corner buttons and </>edge buttons - shared
        across all three modes: a "Capture" button is included whenever self.has_camera (plain
        "camera" mode and "camera_ftp"), omitted when there's no camera to switch back to (plain
        "ftp" mode). Branches on ai_edit settings for the third button: hold-to-talk "Speak" for
        the "voice" input method, a tap-to-open-picker "AI Edit" for "keyboard", or omitted
        entirely when ai_edit.enabled is false.
        """
        specs = []
        if self.has_camera:
            specs.append(("Capture", self.play_button_font, colours.BUTTON_TEXT, colours.PRIMARY, None, self.enter_capture))
        specs.append(("Print", self.play_button_font, colours.BUTTON_TEXT, colours.NEUTRAL, None, self.play_print))
        if self.ai_edit_enabled:
            if self.ai_input_method == "voice":
                specs.append(("Speak", self.play_button_font, colours.BUTTON_TEXT, colours.CONFIRM, self.finish_play_voice_prompt, self.start_voice_prompt))
            else:
                specs.append(("AI Edit", self.play_button_font, colours.BUTTON_TEXT, colours.CONFIRM, None, self.show_ai_prompt_picker))
        specs.append(("Publish", self.play_button_font, colours.BUTTON_TEXT, colours.PUBLISH, None, self.show_publish_menu))

        side_button_width = 80
        side_button_height = 80
        return (
            *self._row_of_buttons(button_y, 50, specs),
            Button(0, 0, # position
                   side_button_width, side_button_height, # size
                   "Stop", # text
                   self.small_font, # font
                   colours.BUTTON_TEXT, # text colour
                   colours.DANGER, # background colour
                   None,  # called when released
                   self.quit_app # called when pressed
                   ),
            Button(self.screen.WIDTH - side_button_width, 0, side_button_width, side_button_height, "Page", self.small_font, colours.BUTTON_TEXT, colours.UTILITY, None, self.show_play_grid),
            Button(0, arrow_y, 32, 100, "<", self.small_font, colours.BUTTON_TEXT, colours.UTILITY, None, self.play_prev_image),
            Button(self.screen.WIDTH - 32, arrow_y, 32, 100, ">", self.small_font, colours.BUTTON_TEXT, colours.UTILITY, None, self.play_next_image),
        )

    # ------------------------------------------------------------
    # Camera-mode hooks - the only mode-specific seams in the shared Play/Publish/Speak/Print
    # flow below: FTP mode (self.has_camera=False) never captures anything itself, so these
    # branch to a no-camera fallback wherever relevant.
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
        """Which button row review_ai_prompt() should restore when the edit wasn't triggered
        from Play mode (e.g. a capture app's remote hold-to-talk, which bypasses Play entirely)."""
        return self.capture_menu if self.has_camera else self.play_menu

    def _empty_play_buttons(self, button_y):
        """Buttons to show under the "no photos yet" banner in show_play_image() - a way back to
        the viewfinder in camera mode, nothing to offer in FTP mode."""
        if not self.has_camera:
            return ()
        return (
            Button(0, button_y, self.screen.WIDTH, 50, "Capture", self.medium_font, colours.BUTTON_TEXT, colours.PRIMARY, None, self.enter_capture),
        )

    def _empty_play_message(self):
        return "No photos yet" if self.has_camera else "Waiting for photos..."

    def adjust_exposure(self, delta):
        new_value = round(min(self.ev_max, max(self.ev_min, self.exposure_value + delta)), 2)
        if new_value == self.exposure_value:
            return
        self.exposure_value = new_value
        self.last_capture_activity = time.monotonic()

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
        self.last_capture_activity = time.monotonic()
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
    # Misc
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # Printing ("Print" button, in Play mode)
    # ------------------------------------------------------------

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
            watermark_path = self.app_dir / self.watermark_settings.get("file", "assets/images/watermark.png")
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
        self.print_status_text = None
        self.print_status_ready.clear()
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
            self.print_result = self.wait_for_print_job(conn, job_id, printer_name)
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

    def wait_for_print_job(self, conn, job_id, printer_name):
        """Polls a submitted job until CUPS reports it finished, one way or another, or a
        timeout elapses. printFile() only confirms the job was queued - without this, a print
        that fails downstream (out of paper, a jam) would look identical to one that actually
        came out. Also refreshes the on-screen status from `lpstat -t` every
        LPSTAT_POLL_SECONDS - see update_print_status_text().
        """
        timeout = self.printing_settings.get("job_timeout_seconds", 120)
        deadline = time.time() + timeout
        reasons = []
        next_lpstat_poll = time.time()  # poll immediately on the first pass, then periodically

        while time.time() < deadline:
            if time.time() >= next_lpstat_poll:
                self.update_print_status_text(printer_name)
                next_lpstat_poll = time.time() + LPSTAT_POLL_SECONDS

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

    def update_print_status_text(self, printer_name):
        """Refreshes print_status_text from `lpstat -t` if it's changed, and signals
        print_status_ready so process_frame() redraws the "Printing..." banner with it -
        mirrors how ai_status_ready forces a redraw when the AI edit progress text changes.
        """
        text = self.poll_lpstat(printer_name)
        if text and text != self.print_status_text:
            self.print_status_text = text
            self.print_status_ready.set()

    def poll_lpstat(self, printer_name):
        """Runs `lpstat -t` and returns this printer's own diagnostic detail line, if it has
        one right now - pycups (the structured CUPS API binding used everywhere else in this
        file) doesn't expose the CLI's free-text status reporting, and that line is exactly
        what's useful for diagnosing a stuck print (paper out, printer offline, a jam) at a
        glance: an indented line following the printer's summary line (e.g. gutenprint's
        "Sending CYAN plane" while printing, or "No paper tray loaded, aborting!" when it
        fails). Everything else `-t` reports (the summary line itself, "device for ..."/
        "accepting requests since ..." lines, the raw job listing) is either boilerplate that
        doesn't change over the course of a print, or duplicates what run_print()/
        wait_for_print_job() already track - so none of that is returned.
        """
        try:
            result = subprocess.run(["lpstat", "-t"], capture_output=True, text=True, timeout=5)
        except (subprocess.SubprocessError, OSError) as e:
            print(f"Could not run lpstat: {e}")
            return None

        prefix = f"printer {printer_name} "
        detail_lines = []
        capture_continuation = False
        for line in result.stdout.splitlines():
            if line.startswith(prefix):
                detail_lines = []
                capture_continuation = True
            elif capture_continuation and line[:1].isspace():
                detail_lines.append(line.strip())
            else:
                capture_continuation = False

        return " ".join(detail_lines) if detail_lines else None

    def finish_print(self):
        self.print_pending = False
        message = self.print_result
        self.print_result = None
        self.print_done.clear()
        self.show_result(self.status_frame(message), hold_seconds=2)
        self.show_play_image()

    # ------------------------------------------------------------
    # Play mode
    # ------------------------------------------------------------

    def enter_play(self):
        """Always lands on the most recently taken/received photo - see show_play_image()."""
        if self.ai_pending or self.publish_pending or self.print_pending:
            return
        if self.has_camera and self.camera_streaming:
            # Play mode never shows the live feed - stopping the sensor here (rather than just
            # leaving capture_request() unpumped) is what actually cuts the CPU/battery cost,
            # since libcamera keeps the ISP running at full tilt as long as the camera is
            # started, whether or not anything's requesting frames from it. enter_capture()
            # restarts it on the way back.
            self.picam2.stop()
            self.camera_streaming = False
            self.frame_ready.clear()
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
            self.screen.set_buttons(self._empty_play_buttons(button_y))
            self.play_view = self.status_frame(self._empty_play_message())
            self.screen.draw(self.play_view)
            return

        path = self.play_images[self.play_index]
        if path == self._play_view_cache_path:
            self.play_view = self._play_view_cache_img
        else:
            try:
                self.play_view = self._place_in_frame(Image.open(path).convert("RGB"))
                self._play_view_cache_path = path
                self._play_view_cache_img = self.play_view
            except Exception as e:
                print(f"Could not load {path}: {e}")
                self.play_view = self.status_frame("Could not load photo")
                self._play_view_cache_path = None

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
                # text is never drawn (visible=False - the thumbnail image is the visual), but
                # Button.do_down()/do_up() print it regardless of visibility, so it still needs
                # a real label - otherwise every grid tap logs a blank "Button:  pressed".
                cell_x, cell_y, cell_w, cell_h, f"thumb{absolute_index}", self.small_font, colours.PRIMARY, colours.PRIMARY,
                up_handler=None, down_handler=(lambda idx=absolute_index: self.select_play_grid_image(idx)), visible=False,
            ))

        self.play_view = canvas

        nav_buttons = self._row_of_buttons(button_y, 50, (
            ("Older", self.medium_font, colours.BUTTON_TEXT, colours.PRIMARY, None, self.play_grid_next_page),
            ("Newer", self.medium_font, colours.BUTTON_TEXT, colours.PRIMARY, None, self.play_grid_prev_page),
            ("Done", self.medium_font, colours.BUTTON_TEXT, colours.NEUTRAL, None, self.show_play_image),
        ))
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

    def _show_new_photo(self, path):
        """Makes `path` the current Play-mode selection and shows it, as if it had just been
        taken/received - used when a new file becomes available outside of the AI-edit flow
        (finish_ai_edit() does the equivalent inline for its own case)."""
        self.play_images.insert(0, path)
        self.play_index = 0
        self.show_play_image()

    # ------------------------------------------------------------
    # Publishing ("Publish" button, in Play mode)
    # ------------------------------------------------------------

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
        specs = [
            (label, self.play_button_font, colours.BUTTON_TEXT,
             self.PUBLISH_MENU_COLOURS.get(publisher_type, colours.NEUTRAL), None,
             lambda publisher_type=publisher_type: self.start_publish(publisher_type))
            for publisher_type, label in options
        ]
        specs.append(("Back", self.play_button_font, colours.BUTTON_TEXT, colours.NEUTRAL, None, self.show_play_image))

        self.screen.set_buttons(self._row_of_buttons(button_y, 50, specs))
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

    def _row_of_buttons(self, y, height, specs, gap=10):
        """Lays out specs - each (text, font, text_colour, back_colour, up_handler,
        down_handler) - as equal-width buttons spanning the full canvas width. Used for every
        menu that's a single row of buttons filling the screen (capture/play menus, grid nav,
        publish picker, the AI confirm/keyboard screens), so they keep filling the screen
        edge-to-edge at whatever display.width is configured, not just the 480px this app
        originally shipped with.
        """
        n = len(specs)
        button_width = (self.screen.WIDTH - gap * (n - 1)) // n
        buttons = []
        x = 0
        for text, font, text_colour, back_colour, up_handler, down_handler in specs:
            buttons.append(Button(x, y, button_width, height, text, font, text_colour, back_colour, up_handler, down_handler))
            x += button_width + gap
        return tuple(buttons)

    def _place_in_frame(self, img):
        """Fits img (preserving aspect ratio) into the content area above the bottom button bar
        (self.screen.WIDTH x self.content_height), centered on a black self.screen.WIDTH x
        self.screen.HEIGHT canvas. Used for anything shown full-screen (the live viewfinder,
        Play-mode photos, AI-edit results) so a source image whose aspect ratio doesn't match the
        screen's - e.g. 4:3 stills on a wider display - gets letterboxed/pillarboxed instead of
        stretched, and stays correct across different display.width/height configs.
        """
        fitted = ImageOps.contain(img, (self.screen.WIDTH, self.content_height))
        canvas = Image.new("RGB", (self.screen.WIDTH, self.screen.HEIGHT), (0, 0, 0))
        offset = (
            (self.screen.WIDTH - fitted.width) // 2,
            (self.content_height - fitted.height) // 2,
        )
        canvas.paste(fitted, offset)
        return canvas

    def status_frame(self, text, font=None):
        """A short status banner over the current backdrop. Word-wraps to as many lines as
        needed - most callers pass a short fixed string that always fits on one line (unchanged
        from before), but a transcribed voice prompt (or an lpstat diagnostic line) can run to a
        full sentence, hence the wrapping and the font override: medium_font (the default) is
        sized for a couple of short words, not a whole sentence.
        """
        font = font or self.medium_font

        if self.mode in ("play", "play_grid") and self.play_view is not None:
            base = self.play_view
        elif getattr(self, "finder", None) is not None:
            base = self.finder
        else:
            base = Image.new("RGB", (self.screen.WIDTH, self.screen.HEIGHT), (0, 0, 0))
        frame = base.copy()
        draw = ImageDraw.Draw(frame)

        max_width = frame.width - 20
        words = text.split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            lines = [text]

        # Matches medium_font's own 32px-font/40px-line ratio, so existing callers (which all
        # use the default font) render exactly as before.
        line_height = round(font.size * 1.25)
        block_height = line_height * len(lines) + 10
        top = frame.height // 2 - block_height // 2
        draw.rectangle((0, top, frame.width, top + block_height), fill=(0, 0, 0))
        for i, line in enumerate(lines):
            y = top + 10 + i * line_height + line_height // 2
            draw.text((frame.width // 2, y), line, font=font, fill=(255, 255, 255), anchor="mm")
        return frame

    def qr_result_frame(self, url, phrase):
        """Shown after a successful publish to custard-cream-server: a QR code linking to the
        picture's page, plus the three-word phrase as a human-readable fallback for anyone who
        can't scan it - drawn over the photo that was just published (rather than a blank
        background), so it stays visible while this screen is up instead of disappearing until
        Done is pressed.
        """
        frame = self.play_view.copy() if self.play_view is not None else Image.new("RGB", (self.screen.WIDTH, self.screen.HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(frame)

        qr_size = 200
        url = url.replace(":3001", "")
        qr_img = qrcode.make(url).convert("RGB").resize((qr_size, qr_size))
        qr_x = 20
        qr_y = frame.height // 2 - qr_size // 2
        frame.paste(qr_img, (qr_x, qr_y))

        # Solid backing panel behind the text only (the QR code already has its own white quiet
        # zone from qrcode.make(), so it stays scannable over the photo without one) - otherwise
        # the "Published!"/phrase text could land on top of light or noisy parts of the photo and
        # become unreadable.
        text_x = qr_x + qr_size + 10
        draw.rectangle((text_x - 10, qr_y, frame.width, qr_y + qr_size), fill=(0, 0, 0))
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
                              colours.BUTTON_TEXT, colours.NEUTRAL, None, done_pressed.set)

        self.screen.set_buttons((done_button,))
        self.screen.draw(img)
        while self.running and not self.screen.quit_requested and not done_pressed.is_set():
            self.screen.update()
            time.sleep(0.05)

    # ------------------------------------------------------------
    # AI-edit prompt picker ("AI Edit" button, ai_edit.input_method == "keyboard")
    # ------------------------------------------------------------

    def _truncate_button_label(self, text, font, max_width):
        """Ellipsis-truncates text to fit max_width when drawn in font. Button.draw() renders a
        single line with no wrapping (unlike status_frame()/the prompt editor below), so a preset
        prompt longer than its button needs shortening for display - the full, untruncated text
        is still what's captured by the closure and sent as the edit instruction.
        """
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        if draw.textlength(text, font=font) <= max_width:
            return text
        while text and draw.textlength(text + "...", font=font) > max_width:
            text = text[:-1]
        return text + "..." if text else "..."

    def show_ai_prompt_picker(self):
        """"AI Edit" button in Play mode when ai_edit.input_method is "keyboard" - pick one of
        the configured preset prompts, or enter a custom one via the existing on-screen keyboard,
        instead of speaking it.

        Non-blocking, the same shape as show_publish_menu(): button handlers here only ever set
        ai_prompt_choice_ready (checked by process_frame(), see handle_ai_prompt_choice()) rather
        than entering the blocking confirm/edit screens directly. That distinction matters -
        every blocking review screen in this file (show_ai_confirm_screen, show_ai_edit_screen,
        show_result_until_done, _prompt_and_send_ai_edit) is only ever entered from
        process_frame()'s own body, never from inside a button's down_handler/up_handler: handlers
        run from inside ButtonPanel.update(), itself called from self.screen.update() - entering a
        blocking `while ...: self.screen.update()` loop from there would re-enter screen.update()
        from inside itself.
        """
        if not self.play_images or self.ai_pending or self.print_pending:
            return

        # Normally set by finish_voice_prompt() - this input method bypasses that, so set it here.
        self.ai_still_path = self.play_images[self.play_index]

        presets = self.ai_edit_settings.get("presets", [])
        button_y = self.screen.HEIGHT - 50
        cols = 2
        rows = max(1, -(-len(presets) // cols))  # ceil division
        cell_w = self.screen.WIDTH // cols
        cell_h = button_y // rows

        preset_buttons = []
        for i, text in enumerate(presets):
            col, row = i % cols, i // cols
            label = self._truncate_button_label(text, self.play_button_font, cell_w - 20)
            preset_buttons.append(Button(
                col * cell_w, row * cell_h, cell_w, cell_h, label, self.play_button_font,
                colours.BUTTON_TEXT, colours.PRESET, None,
                lambda text=text: self._choose_ai_prompt(text),
            ))

        nav_buttons = self._row_of_buttons(button_y, 50, (
            ("Custom...", self.play_button_font, colours.BUTTON_TEXT, colours.NEUTRAL, None, self._choose_ai_prompt_custom),
            ("Back", self.play_button_font, colours.BUTTON_TEXT, colours.DANGER, None, self.show_play_image),
        ))

        self.screen.set_buttons((*preset_buttons, *nav_buttons))
        self.screen.draw(self.play_view)

    def _choose_ai_prompt(self, text):
        self.ai_prompt_choice_text = text
        self.ai_prompt_choice_is_custom = False
        self.ai_prompt_choice_ready.set()

    def _choose_ai_prompt_custom(self):
        self.ai_prompt_choice_is_custom = True
        self.ai_prompt_choice_ready.set()

    def handle_ai_prompt_choice(self):
        """Runs on the main thread once process_frame() sees ai_prompt_choice_ready - safe to
        block here (see show_ai_prompt_picker()'s docstring): the custom-entry keyboard and the
        Send/Reject/Edit confirm screen it feeds into are only entered from this call depth.
        """
        is_custom = self.ai_prompt_choice_is_custom
        text = self.ai_prompt_choice_text
        self.ai_prompt_choice_text = None
        self.ai_prompt_choice_is_custom = False

        if is_custom:
            text = self.show_ai_edit_screen("")
            if not text:
                self.show_play_image()
                return

        self._prompt_and_send_ai_edit(text, came_from_play=True)

    def start_voice_prompt(self):
        if self.ai_pending or self.print_pending:
            return
        if self.has_camera and self.mode == "capture":
            # Remote-triggered Speak bypasses the on-screen capture_menu buttons entirely, so it
            # needs its own idle-timer reset - see self.last_capture_activity above.
            self.last_capture_activity = time.monotonic()
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
            still_path = self._capture_fresh_still()
        else:
            still_path = image_path
            print(f"Speak: using existing photo {still_path}")

        self.ai_pending = True
        self.ai_still_path = still_path
        self.ai_transcript = None
        self.ai_transcribe_done.clear()
        self.ai_status_text = None
        self.ai_status_ready.clear()
        Thread(target=self.run_transcribe, daemon=True).start()

    def run_transcribe(self):
        """Runs on a background thread: the transcription-only phase (network call for the
        Gemini backend, local/instant for Vosk). Split out from image editing so the result can
        be reviewed - accepted, rejected, or edited - before anything is sent to Gemini for the
        actual image edit.
        """
        try:
            self.ai_status_text = "Transcribing..."
            self.ai_status_ready.set()
            self.ai_transcript = self.transcriber.finalize()
        except Exception as e:
            print(f"Speak: transcription failed: {e}")
            self.ai_transcript = None
        finally:
            self.ai_transcribe_done.set()

    def review_ai_prompt(self):
        """Runs on the main thread once run_transcribe() finishes (called from process_frame()).
        Shows the transcribed prompt and lets the user Send/Reject/Edit it before anything is
        sent to Gemini for the image edit - blocks the main loop while doing so, the same way
        show_result_until_done() already does for the publish QR screen.
        """
        text = self.ai_transcript
        self.ai_transcript = None
        self.ai_transcribe_done.clear()
        came_from_play = self.mode == "play"

        if not text:
            print("Speak: didn't catch that")
            self.ai_pending = False
            self.show_result(self.status_frame("Didn't catch that"), hold_seconds=2)
            if came_from_play:
                self.show_play_image()
            return

        self._prompt_and_send_ai_edit(text, came_from_play)

    def _prompt_and_send_ai_edit(self, text, came_from_play):
        """Runs the confirm/edit loop for `text` and either kicks off run_ai_edit or abandons the
        edit - shared by review_ai_prompt()'s first pass after transcription and by
        finish_ai_edit() retrying the same prompt after a failed edit (server unavailable, error
        response, etc.), so a failure lands the user back on the editable prompt instead of just
        an error banner.
        """
        while True:
            choice = self.show_ai_confirm_screen(text)
            if choice == "edit":
                text = self.show_ai_edit_screen(text)
                continue
            break

        # The confirm/edit screens took over screen.set_buttons() for their own controls -
        # restore whichever menu was active before Speak was pressed, same as the rest of this
        # flow (print/publish/the original combined AI edit) leaves untouched during their
        # own "processing" banners rather than clearing it.
        self.screen.set_buttons(self.play_menu if came_from_play else self._non_play_menu())

        if choice == "reject":
            print("Speak: prompt rejected, not sent")
            self.ai_pending = False
            if came_from_play:
                self.show_play_image()
            return

        self.ai_pending = True
        self.ai_result = None
        self.ai_done.clear()
        self.ai_status_text = None
        self.ai_status_ready.clear()
        Thread(target=self.run_ai_edit, args=(self.ai_still_path, text), daemon=True).start()

    def show_ai_confirm_screen(self, text):
        """Blocks (same idiom as show_result_until_done(): redraw only when a button fires) until
        the user picks what to do with the transcribed prompt. Returns "send", "reject", or
        "edit" - never sends anything to Gemini itself, that's run_ai_edit()'s job.
        """
        choice = {"value": None}

        def pick(value):
            choice["value"] = value

        buttons = self._row_of_buttons(self.screen.HEIGHT - 50, 50, (
            ("Reject", self.play_button_font, colours.BUTTON_TEXT, colours.DANGER, None, lambda: pick("reject")),
            ("Edit", self.play_button_font, colours.BUTTON_TEXT, colours.NEUTRAL, None, lambda: pick("edit")),
            ("Send", self.play_button_font, colours.BUTTON_TEXT, colours.CONFIRM, None, lambda: pick("send")),
        ))
        self.screen.set_buttons(buttons)
        self.screen.draw(self.status_frame(text))
        while self.running and not self.screen.quit_requested and choice["value"] is None:
            self.screen.update()
            time.sleep(0.05)
        return choice["value"] or "reject"

    def show_ai_edit_screen(self, initial_text):
        """On-screen keyboard for correcting a misheard prompt before it's sent - built entirely
        from Button/ButtonPanel, no new display-backend code. Cancel returns initial_text
        unchanged; Done returns whatever's in the buffer at that point. Editing is append/
        backspace/cursor-move at a single cursor position (no shift/caps, no newline key) -
        prompts are natural-language Gemini instructions, not code, so this covers the need
        without a full mobile-keyboard's scope.
        """
        state = {"text": initial_text, "cursor": len(initial_text), "done": None}

        def insert(ch):
            text, cursor = state["text"], state["cursor"]
            state["text"] = text[:cursor] + ch + text[cursor:]
            state["cursor"] = cursor + len(ch)

        def backspace():
            text, cursor = state["text"], state["cursor"]
            if cursor > 0:
                state["text"] = text[:cursor - 1] + text[cursor:]
                state["cursor"] = cursor - 1

        def move_cursor(delta):
            state["cursor"] = max(0, min(len(state["text"]), state["cursor"] + delta))

        def clear_text():
            state["text"] = ""
            state["cursor"] = 0

        def finish(value):
            state["done"] = value

        unit = self.screen.WIDTH / 10
        key_row_height = 50
        keys_top = self.screen.HEIGHT - 50 - 4 * key_row_height

        def key_row(row_index, specs):
            """specs: list of (label, units, handler). Lays keys out left-to-right on the
            unit grid, at the given row within the 4-row key area."""
            y = keys_top + row_index * key_row_height
            buttons = []
            x = 0.0
            for label, units, handler in specs:
                width = round(units * unit)
                buttons.append(Button(round(x), y, width, key_row_height, label, self.medium_font,
                                       colours.BUTTON_TEXT, colours.UTILITY, None, handler))
                x += units * unit
            return buttons

        letter_keys = []
        for ch in "qwertyuiop":
            letter_keys.append((ch, 1, lambda ch=ch: insert(ch)))
        row1 = key_row(0, letter_keys)

        letter_keys = [(ch, 1, lambda ch=ch: insert(ch)) for ch in "asdfghjkl"]
        letter_keys.append(("Del", 1, backspace))
        row2 = key_row(1, letter_keys)

        letter_keys = [(ch, 1, lambda ch=ch: insert(ch)) for ch in "zxcvbnm"]
        letter_keys.append(("<", 1.5, lambda: move_cursor(-1)))
        letter_keys.append((">", 1.5, lambda: move_cursor(1)))
        row3 = key_row(2, letter_keys)

        row4 = key_row(3, [
            ("Space", 6, lambda: insert(" ")),
            (".", 1, lambda: insert(".")),
            (",", 1, lambda: insert(",")),
            ("'", 1, lambda: insert("'")),
            ("?", 1, lambda: insert("?")),
        ])

        action_buttons = self._row_of_buttons(self.screen.HEIGHT - 50, 50, (
            ("Cancel", self.play_button_font, colours.BUTTON_TEXT, colours.DANGER, None, lambda: finish(initial_text)),
            ("Clear", self.play_button_font, colours.BUTTON_TEXT, colours.NEUTRAL, None, clear_text),
            ("Done", self.play_button_font, colours.BUTTON_TEXT, colours.CONFIRM, None, lambda: finish(state["text"])),
        ))

        self.screen.set_buttons((*row1, *row2, *row3, *row4, *action_buttons))

        text_area = (0, 0, self.screen.WIDTH, keys_top)
        self.screen.draw(self._render_prompt_editor(state["text"], state["cursor"], text_area))
        while self.running and not self.screen.quit_requested and state["done"] is None:
            if self.screen.update():
                self.screen.draw(self._render_prompt_editor(state["text"], state["cursor"], text_area))
            time.sleep(0.02)
        return state["done"] if state["done"] is not None else initial_text

    def _render_prompt_editor(self, text, cursor, area):
        """Draws `text` word-wrapped and left-aligned into `area` = (x, y, width, height), with a
        vertical bar marking `cursor`'s position, scrolling to keep the cursor's line visible if
        the wrapped text is taller than the area. A dedicated renderer rather than a status_frame()
        reuse: status_frame() is a centered read-only banner, and this needs left-aligned wrapping
        plus a cursor and scrolling, which don't fit that shape.
        """
        x, y, width, height = area
        frame = Image.new("RGB", (self.screen.WIDTH, self.screen.HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(frame)
        font = self.small_font

        max_width = width - 20
        words = text.split(" ")
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if draw.textlength(candidate, font=font) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)

        # Recover each line's (start, end) offset into the original text, so the line containing
        # `cursor` - and the pixel x-offset within it - can be found. Safe to locate lines via
        # sequential text.index() here since Space always inserts single ASCII spaces, so
        # rejoining words with single spaces reproduces the original spacing exactly.
        spans = []
        search_from = 0
        for line in lines:
            start = text.index(line, search_from)
            end = start + len(line)
            spans.append((start, end))
            search_from = end

        cursor_line = 0
        for i, (start, end) in enumerate(spans):
            if start <= cursor <= end:
                cursor_line = i
                break
            cursor_line = i

        line_height = round(font.size * 1.3)
        max_visible = max(1, height // line_height)
        window_start = max(0, min(cursor_line - max_visible // 2, len(lines) - max_visible))
        visible_lines = lines[window_start:window_start + max_visible]

        for i, line in enumerate(visible_lines):
            line_y = y + 10 + i * line_height
            draw.text((x + 10, line_y), line, font=font, fill=(255, 255, 255))

            line_index = window_start + i
            if line_index == cursor_line:
                start, _ = spans[line_index]
                prefix = text[start:cursor]
                cursor_x = x + 10 + draw.textlength(prefix, font=font)
                draw.line((cursor_x, line_y, cursor_x, line_y + line_height - 2), fill=(255, 255, 0), width=2)

        return frame

    def run_ai_edit(self, still_path, prompt_text):
        """Runs on a background thread so the viewfinder/buttons stay responsive while waiting on
        the network. Transcription has already happened (and been reviewed) by this point -
        this is just the Gemini image-edit call."""
        try:
            self.ai_status_text = "Sending image for processing..."
            self.ai_status_ready.set()
            client = self.get_custard_cream_client()
            edited_bytes = client.edit_image(still_path.read_bytes(), prompt_text)
            if edited_bytes is None:
                self.ai_result = ("status", "No image returned", prompt_text)
            else:
                self.ai_status_text = "Received result, saving..."
                self.ai_status_ready.set()
                self.ai_result = ("image", edited_bytes, prompt_text)
        except Exception as e:
            print(f"Speak: AI edit failed: {e}")
            self.ai_result = ("status", "AI edit failed", prompt_text)
        finally:
            self.ai_done.set()

    def finish_ai_edit(self):
        self.ai_pending = False
        result = self.ai_result
        self.ai_result = None
        self.ai_done.clear()
        came_from_play = self.mode == "play"

        try:
            if result is None:
                return

            if result[0] == "status":
                # A failed edit (server unavailable, an error response, no image back) shouldn't
                # just dump the user out with an error banner and the prompt lost - land them
                # back on the same editable prompt so they can adjust and resend, or reject, via
                # the same confirm/edit loop review_ai_prompt() used the first time round.
                _, message, prompt_text = result
                self.show_result(self.status_frame(message), hold_seconds=2)
                self._prompt_and_send_ai_edit(prompt_text, came_from_play)
                return

            _, image_bytes, prompt_text = result
            ts = time.strftime("%Y%m%d_%H%M%S")
            out_path = self.save_dir / f"ai_{ts}.jpg"
            out_path.write_bytes(image_bytes)
            self.last_photo_path = out_path
            self.ai_prompts_by_path[out_path] = prompt_text
            print(f"Saved {out_path} (prompt: {prompt_text!r})")

            result_img = self._place_in_frame(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
            self.show_result(result_img, hold_seconds=self.custard_cream_settings.get("result_hold_seconds", 4))

            if came_from_play:
                self.play_images.insert(0, out_path)
                self.play_index = 0
        finally:
            # Only if this edit was triggered from Play mode - the remote's direct hold-to-talk
            # never touches Play mode, so this is a no-op for that path. Skipped while a retry
            # from the status branch above just kicked off another run_ai_edit (ai_pending is
            # back to True): that leaves the "Sending image for processing..." status in place
            # instead of flashing back to the play image underneath it.
            if came_from_play and not self.ai_pending:
                self.show_play_image()

    # ------------------------------------------------------------
    # Capture mode <-> Play mode (camera mode only)
    # ------------------------------------------------------------

    def enter_capture(self):
        self.mode = "capture"
        if self.has_camera and not self.camera_streaming:
            self.picam2.start()
            self.camera_streaming = True
            self.request_next_frame()
        self.last_capture_activity = time.monotonic()
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
        return self._place_in_frame(frame)

    def request_next_frame(self):
        self.pending_job = self.picam2.capture_request(
            wait=False,
            signal_function=lambda job: self.frame_ready.set()
        )

    def process_frame(self):
        # Snapshot before anything below runs a button handler (screen.update() dispatches
        # down/up_handlers synchronously) - most Play-mode navigation handlers (show_play_image(),
        # show_publish_menu(), etc.) already call self.screen.draw() themselves. Without this,
        # the "if dirty" redraw below would repaint the exact same frame a second time on every
        # single tap - a real cost on slow hardware, and the dominant one in FTP mode, which has
        # no live camera frame to compete with it.
        draw_count_before_tick = self.screen.draw_count

        dirty = False

        if self.has_camera:
            if self.camera_streaming and self.frame_ready.is_set():
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

            if (
                self.idle_timeout_enabled
                and self.mode == "capture"
                and not self.voice_recording
                and not self.ai_pending
                and not self.publish_pending
                and not self.print_pending
                and time.monotonic() - self.last_capture_activity >= self.idle_timeout_seconds
            ):
                # Capture mode left untouched for a while - switch to Play, which stops the
                # camera (see enter_play()), rather than leaving the sensor streaming
                # unattended. Guarded against the busy states above so it can't cut in mid
                # voice-recording/AI-edit/publish/print.
                self.enter_play()

        if self.has_ftp:
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

        if self.ai_prompt_choice_ready.is_set():
            self.ai_prompt_choice_ready.clear()
            self.handle_ai_prompt_choice()
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

        if dirty and self.screen.draw_count == draw_count_before_tick:
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

    def _splash_frame(self):
        """Startup splash - version number and project URL, shown briefly by run() before the
        live viewfinder/play view takes over, so a build's version is visible without digging
        through files on the device."""
        frame = Image.new("RGB", (self.screen.WIDTH, self.screen.HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(frame)
        cx, cy = frame.width // 2, frame.height // 2
        draw.text((cx, cy - 40), "Custard Cream Camera", font=self.large_font, fill=(255, 255, 255), anchor="mm")
        draw.text((cx, cy + 10), f"Version {self.version}", font=self.medium_font, fill=(200, 200, 200), anchor="mm")
        draw.text((cx, cy + 50), GITHUB_URL, font=self.small_font, fill=(120, 180, 255), anchor="mm")
        return frame

    def run(self):
        self.running = True
        try:
            # Blank the button row for the splash - self.screen.set_buttons() was already called
            # in __init__ with whichever menu applies (capture_menu/play_menu), so without this
            # those buttons would be drawn overlaid on the splash text.
            self.screen.set_buttons(())
            self.show_result(self._splash_frame(), hold_seconds=2)
            self.screen.set_buttons(self.capture_menu if self.mode == "capture" else self.play_menu)
            if self.mode in ("play", "play_grid"):
                # Camera mode self-heals: the live viewfinder marks itself dirty every frame
                # once streaming resumes, so the splash gets painted over within one frame
                # period regardless. Play mode (FTP mode's resting screen, always landed on via
                # enter_play() before the splash was drawn over it) has no such heartbeat -
                # process_frame() only redraws on a button press or an incoming photo - so
                # without this the splash would stay on screen indefinitely.
                self.screen.draw(self.play_view)

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

                if not self.has_camera or not self.camera_streaming:
                    # Nothing paces this loop in FTP mode, or in Play mode once the camera's
                    # stopped (see enter_play()), the way frame_ready does while the camera is
                    # actively streaming - avoid spinning at full CPU polling empty state.
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
                if self.gpio_remote is not None:
                    self.gpio_remote.stop()
                self.picam2.stop()
            if self.has_ftp:
                self.ftp_receiver.stop()
            self.screen.close()
            self.kbd.close()


def main():
    custard_cream_camera = CustardCreamCamera()
    custard_cream_camera.run()


if __name__ == "__main__":
    main()
