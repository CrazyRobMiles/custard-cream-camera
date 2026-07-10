import selectors
import threading

try:
    import evdev
except ImportError:
    evdev = None


class ShutterRemote:
    """Listens for specific keys (e.g. the Volume Up key Bluetooth camera remotes send in "iOS"
    mode, or Enter in "Android" mode) on connected input devices, and calls the bound on_down/
    on_up callback when that key is pressed/released.

    Reads the raw input event directly via evdev rather than relying on window/keyboard focus,
    so it works the same regardless of what's on screen - matching how a physical button should
    behave. Reports both press and release so callers can implement press-and-hold actions (like
    hold-to-talk) the same way the on-screen buttons do, not just single-shot triggers.
    """

    def __init__(self, bindings, device_name=None, grab=False):
        """bindings: {key_name: (on_down, on_up)} - either callback may be None."""
        self.bindings = bindings
        self.device_name = device_name
        self.grab = grab
        self.thread = None
        self.running = False
        self.devices = []

    def start(self):
        if evdev is None:
            print("ShutterRemote: python-evdev not installed, remote trigger disabled")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _open_devices(self):
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        if self.device_name:
            devices = [d for d in devices if self.device_name.lower() in d.name.lower()]

        if self.grab:
            for d in devices:
                try:
                    d.grab()
                except Exception as e:
                    print(f"ShutterRemote: could not grab '{d.name}': {e}")

        return devices

    def _run(self):
        self.devices = self._open_devices()
        if not self.devices:
            print("ShutterRemote: no matching input devices found - is the remote paired and connected?")
            return

        print("ShutterRemote: listening on " + ", ".join(d.name for d in self.devices))

        sel = selectors.DefaultSelector()
        for d in self.devices:
            sel.register(d, selectors.EVENT_READ)

        while self.running:
            for key, _ in sel.select(timeout=1):
                device = key.fileobj
                try:
                    for event in device.read():
                        self._handle_event(event)
                except OSError:
                    print(f"ShutterRemote: '{device.name}' disconnected")
                    sel.unregister(device)

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
