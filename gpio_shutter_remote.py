try:
    from gpiozero import Button as GPIOButton
except ImportError:
    GPIOButton = None


class GpioShutterRemote:
    """Listens on a physical push-button switch wired directly to a GPIO pin (e.g. GPIO26 pulled
    to ground when pressed) and calls on_click each time it's pressed.

    Uses gpiozero's Button, which debounces and edge-detects via the pin's own interrupt rather
    than polling - so unlike ShutterRemote/SerialShutterRemote there's no background retry loop:
    a GPIO pin doesn't come and go mid-session the way a Bluetooth/USB device can.
    """

    def __init__(self, pin, on_click, active_low=True, bounce_time=0.05):
        self.pin = pin
        self.on_click = on_click
        self.active_low = active_low
        self.bounce_time = bounce_time
        self.button = None

    def start(self):
        if GPIOButton is None:
            print("GpioShutterRemote: gpiozero not installed, GPIO shutter trigger disabled")
            return
        try:
            # pull_up=True: pin idles high, switch pulls it low when pressed (active low).
            # pull_up=False: pin idles low (internal pull-down), switch pulls it high when
            # pressed (active high) - requires the switch to be wired to the supply rail, not
            # ground.
            self.button = GPIOButton(self.pin, pull_up=self.active_low, bounce_time=self.bounce_time)
        except Exception as e:
            print(f"GpioShutterRemote: could not open GPIO{self.pin} ({e})")
            return
        self.button.when_pressed = self.on_click
        level = "low" if self.active_low else "high"
        print(f"GpioShutterRemote: listening on GPIO{self.pin} (active {level})")

    def stop(self):
        if self.button is not None:
            self.button.close()
            self.button = None
