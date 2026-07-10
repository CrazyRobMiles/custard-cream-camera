import selectors
import threading
import time

try:
    import evdev
except ImportError:
    evdev = None

RETRY_SECONDS = 5


class ShutterRemote:
    """Listens for specific keys (e.g. the Volume Up key Bluetooth camera remotes send in "iOS"
    mode, or Enter in "Android" mode) on connected input devices, and calls the bound on_down/
    on_up callback when that key is pressed/released.

    Reads the raw input event directly via evdev rather than relying on window/keyboard focus,
    so it works the same regardless of what's on screen - matching how a physical button should
    behave. Reports both press and release so callers can implement press-and-hold actions (like
    hold-to-talk) the same way the on-screen buttons do, not just single-shot triggers.

    Bluetooth remotes routinely disconnect (to save battery) and reconnect on the next press, and
    may not even be connected yet when the app starts - so device discovery isn't a one-shot check,
    it keeps retrying for as long as the remote isn't found or drops out.

    Which input device(s) to use is normally discovered automatically: since the caller already
    knows exactly which keys it cares about (via `bindings`), devices are auto-selected by
    capability - does this device report KEY_VOLUMEUP/KEY_ENTER/whatever's bound at all? - rather
    than needing a device name configured up front. `device_name` remains available as a manual
    override if auto-discovery ever picks up more than intended.
    """

    def __init__(self, bindings, device_name=None, grab=False):
        """bindings: {key_name: (on_down, on_up)} - either callback may be None."""
        self.bindings = bindings
        self.device_name = device_name
        self.grab = grab
        self.thread = None
        self.running = False
        self.devices = []

        # The exact key codes we care about (e.g. KEY_VOLUMEUP, KEY_ENTER) - used to auto-select
        # matching devices by capability when device_name isn't given, so there's nothing to look
        # up/configure manually: a device either reports one of these keys or it doesn't.
        self.bound_codes = set()
        if evdev is not None:
            for name in bindings:
                code = evdev.ecodes.ecodes.get(name)
                if code is not None:
                    self.bound_codes.add(code)

    def start(self):
        if evdev is None:
            print("ShutterRemote: python-evdev not installed, remote trigger disabled")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _reports_bound_key(self, device):
        key_caps = device.capabilities().get(evdev.ecodes.EV_KEY, [])
        return any(code in self.bound_codes for code in key_caps)

    def _open_devices(self):
        devices = []
        for path in evdev.list_devices():
            try:
                devices.append(evdev.InputDevice(path))
            except OSError as e:
                # Most commonly a permission error - print it rather than silently dropping the
                # device, since a permissions problem otherwise looks identical to "not found".
                print(f"ShutterRemote: could not open {path}: {e}")

        if self.device_name:
            # Explicit override: trust it completely, no capability filtering.
            devices = [d for d in devices if self.device_name.lower() in d.name.lower()]
        else:
            # Auto-discovery: only devices that actually report one of our bound keys. This is
            # also what makes "grab" safe without device_name - it can never end up grabbing a
            # touchscreen/mouse/keyboard that has nothing to do with photo_key/speak_key.
            devices = [d for d in devices if self._reports_bound_key(d)]

        if self.grab:
            for d in devices:
                try:
                    d.grab()
                except Exception as e:
                    print(f"ShutterRemote: could not grab '{d.name}': {e}")

        return devices

    def _run(self):
        while self.running:
            self.devices = self._open_devices()
            if not self.devices:
                print(f"ShutterRemote: no matching input devices found - retrying every {RETRY_SECONDS}s "
                      "(is the remote paired and connected?)")
                time.sleep(RETRY_SECONDS)
                continue

            print("ShutterRemote: listening on " + ", ".join(d.name for d in self.devices))
            self._listen()
            # _listen() returns once every device has disconnected - loop back and retry discovery
            # rather than giving up, so a remote that reconnects later gets picked back up.

    def _listen(self):
        sel = selectors.DefaultSelector()
        for d in self.devices:
            sel.register(d, selectors.EVENT_READ)

        while self.running and self.devices:
            for key, _ in sel.select(timeout=1):
                device = key.fileobj
                try:
                    for event in device.read():
                        self._handle_event(event)
                except OSError:
                    print(f"ShutterRemote: '{device.name}' disconnected")
                    sel.unregister(device)
                    self.devices.remove(device)

    def _handle_event(self, event):
        if event.type != evdev.ecodes.EV_KEY or event.value not in (0, 1):  # skip autorepeat (2)
            return

        keycode = evdev.categorize(event).keycode
        names = keycode if isinstance(keycode, list) else [keycode]

        for name in names:
            binding = self.bindings.get(name)
            if binding is not None:
                on_down, on_up = binding
                handler = on_down if event.value == 1 else on_up
                if handler:
                    handler()
                return

    def stop(self):
        self.running = False
        for d in self.devices:
            try:
                if self.grab:
                    d.ungrab()
                d.close()
            except Exception:
                pass
