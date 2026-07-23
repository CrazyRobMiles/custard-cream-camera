import threading
import time

try:
    import serial
except ImportError:
    serial = None

RETRY_SECONDS = 1


class SerialShutterRemote:
    """Listens on a USB-serial wired remote that sends the word "click" (newline-terminated)
    each time its button is pressed, and calls on_click when it does.

    Mirrors ShutterRemote's (see shutter_remote.py) retry/reconnect behaviour: the port may not
    exist yet when the app starts, or may disappear mid-session (unplugged, USB glitch), so
    discovery/reading isn't a one-shot attempt - it keeps retrying for as long as the port isn't
    open, rather than giving up.
    """

    def __init__(self, port, on_click, baud_rate=9600, trigger_word="click"):
        self.port = port
        self.on_click = on_click
        self.baud_rate = baud_rate
        self.trigger_word = trigger_word.lower()
        self.thread = None
        self.running = False
        self.connection = None
        self._reported_not_found = False

    def start(self):
        if serial is None:
            print("SerialShutterRemote: pyserial not installed, wired remote disabled")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            except serial.SerialException as e:
                # Only reported on the transition into "not found" - at a 1s retry interval this
                # would otherwise print continuously for as long as the port stays missing.
                if not self._reported_not_found:
                    print(f"SerialShutterRemote: could not open {self.port} ({e}) - "
                          f"retrying every {RETRY_SECONDS}s")
                    self._reported_not_found = True
                time.sleep(RETRY_SECONDS)
                continue

            self._reported_not_found = False
            print(f"SerialShutterRemote: listening on {self.port}")
            self._listen()
            # _listen() returns once the port drops out - loop back and retry discovery rather
            # than giving up, so a remote unplugged/replugged mid-session gets picked back up.

    def _listen(self):
        while self.running and self.connection is not None:
            try:
                line = self.connection.readline().decode(errors="replace").strip()
            except (serial.SerialException, OSError) as e:
                print(f"SerialShutterRemote: '{self.port}' disconnected ({e})")
                break

            if line.lower() == self.trigger_word:
                self.on_click()

        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None

    def stop(self):
        self.running = False
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
