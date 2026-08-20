import io
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from threading import Event, Thread

import cups
import qrcode
from PIL import Image, ImageDraw, ImageOps

from displays import Button, colours
from NanoBananaClient import CustardCreamClient
from print_overlays import apply_datestamp, apply_watermark
from publishers import available_publishers, create_publisher, publisher_label

# IPP job-state values (RFC 8011 SS5.3.7) - pycups surfaces the raw int rather than named
# constants, so the ones this code checks for are spelled out here instead.
CUPS_JOB_STATE_CANCELED = 7
CUPS_JOB_STATE_ABORTED = 8
CUPS_JOB_STATE_COMPLETED = 9

# How often wait_for_print_job() refreshes the on-screen status from `lpstat -t` while a print
# is in flight - frequent enough to catch a paper-out/jam message promptly, without spawning a
# subprocess on every 1s job-state poll.
LPSTAT_POLL_SECONDS = 5


class ReviewStationMixin:
    """Everything about browsing, printing, publishing, and voice-editing photos that are
    already sitting in `self.save_dir` - shared between the camera app (where they arrive via
    a live capture) and the FTP host app (where they arrive over the network). None of this
    touches a camera; it only ever reads/writes files in save_dir and draws through self.screen.

    A subclass must set up, in its own __init__, everything this mixin reads from self:
    settings, screen, app_dir, save_dir, the font set (small_font/medium_font/large_font/
    play_button_font/phrase_font), play_menu, mode/play_images/play_index/play_page/play_view,
    ai_prompts_by_path, the AI-edit Event/flag set, ai_edit_settings/ai_prompt_choice_text/
    ai_prompt_choice_is_custom/ai_prompt_choice_ready, custard_cream_settings/custard_cream_client/
    transcriber (None unless ai_edit is enabled with input_method "voice"), the publish Event/flag
    set + publishers cache dict, the print Event/flag set + printer_name/printing_settings/
    print_test_mode/print_test_dir, watermark_settings/datestamp_settings, audio_output_settings,
    running, and last_photo_path.

    Three seams let a camera-less subclass opt out of the only genuinely camera-specific bits:
    _capture_fresh_still(), _non_play_menu(), and _empty_play_buttons()/_empty_play_message().
    """

    # Button colour per destination, shown in the publish menu - falls back to grey for any
    # publisher type not listed here.
    PUBLISH_MENU_COLOURS = {
        "flickr": colours.PUBLISH,
        "bsky": colours.BSKY,
        "custard_cream_server": colours.CUSTARD_CREAM_SERVER,
    }

    # ------------------------------------------------------------
    # Hooks a camera-less subclass doesn't need to override (defaults are the "no camera" case)
    # ------------------------------------------------------------

    def _capture_fresh_still(self):
        """Only reached if finish_voice_prompt() is called with image_path=None - i.e. only
        relevant to a subclass with an actual camera to capture from."""
        raise NotImplementedError(
            "This app has no camera to capture a fresh still from - always pass an image_path "
            "to finish_voice_prompt()."
        )

    def _non_play_menu(self):
        """Which button row review_ai_prompt() should restore when the edit wasn't triggered
        from Play mode (e.g. a capture app's remote hold-to-talk, which bypasses Play entirely).
        Never reached by an app with no such other mode."""
        return self.play_menu

    def _empty_play_buttons(self, button_y):
        """Buttons to show under the "no photos yet" banner in show_play_image(). A capture app
        offers a way back to its viewfinder; an app with no other mode has nothing to offer."""
        return ()

    def _empty_play_message(self):
        return "No photos yet"

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
            # (custard_cream_camera.py) restarts it on the way back.
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
