# Shutter Remotes

The app supports three independent physical shutter remotes — a Bluetooth one, a wired USB-serial one, and a plain GPIO push-button — each with its own `"enabled"` flag in [settings.json](../settings.json.example), so any or all can be active at once.

## Bluetooth Shutter Remote

Cheap Bluetooth camera remotes don't have a real "pairing mode" — they just have two buttons/positions (labelled iOS/Android or similar) that each send a different key, since iOS and Android camera apps historically listened for different shortcuts. [shutter_remote.py](../shutter_remote.py) listens for both directly at the input-device level (via `evdev`), independent of which window has focus:

* **iOS** button → Volume Up (`KEY_VOLUMEUP`) → takes a photo in [Capture mode](home-screen-modes.md), the same action as the **Click** button - or, if you're currently in Play mode reviewing photos, switches back to Capture mode without taking a photo.
* **Android** button → Enter (`KEY_ENTER`) → hold-to-talk, the same as **Play** mode's **Speak** button: pressing starts recording, releasing sends it. Unlike the photo key, this works from any mode - it always acts on a fresh capture, bypassing Play mode entirely. This relies on the remote sending a genuine press-then-release pair for a physical hold, which is normal HID keyboard behavior, but worth confirming for your specific unit (see below).

To enable it:

1. Set `"shutter_remote": {"enabled": true}` in [settings.json](../settings.json.example).
2. Make sure your user can read input devices: `sudo usermod -aG input $USER`, then log out and back in (or reboot) for group membership to take effect.

The Volume Up mapping is easy to confirm: pressing the iOS button should show your desktop's volume OSD. The Enter mapping is a best guess for "Android mode" on these remotes — if it doesn't trigger recording, confirm the actual key it sends (see below), and set `"photo_key"`/`"speak_key"` in `settings.json` to match (either can be set to `null` to disable that mapping without disabling the other).

### Automatic device discovery

`"device_name"` normally doesn't need to be set at all. `shutter_remote.py` already knows exactly which keys it cares about (`photo_key`/`speak_key`), so with `"device_name": null` it auto-selects any connected input device that reports supporting one of those keys — asking each device "can you send `KEY_VOLUMEUP`/`KEY_ENTER`?" rather than needing to be told a product name up front. This is also what makes `"grab": true` safe by default: it can only ever grab a device that actually reports one of those two keys, never your touchscreen, mouse, or keyboard, since none of those report `KEY_VOLUMEUP`/`KEY_ENTER` as a capability.

Startup then prints just the auto-selected devices, e.g.:
```
ShutterRemote: listening on AB Shutter3        Keyboard, AB Shutter3        Consumer Control
```
Bluetooth "combo" remotes like this commonly register as *two* separate logical devices, since Enter and Volume Up/Down live on different HID pages (`Keyboard` vs `Consumer Control`) — both get auto-selected independently since each reports one of the two keys.

**Caveat:** capability matching can occasionally over-match — e.g. many USB audio adapters/microphones expose a "media control" HID interface reporting `KEY_VOLUMEUP`/`KEY_VOLUMEDOWN`/`KEY_MUTE` even without physical buttons, purely as part of the USB Audio Class spec, so one could get auto-selected too (and grabbed, if `"grab": true"`, though this shouldn't affect its actual audio capture - that's a separate USB interface). Usually harmless, since it'd only matter if that device ever emits a real `KEY_VOLUMEUP` event, but if something unrelated seems to be triggering captures, or you'd rather target the remote precisely, set `"device_name"` to its name (visible in the startup log above, or via `evtest`) to bypass capability matching entirely for an explicit name match instead:
```bash
sudo apt install evtest
sudo evtest   # pick your remote from the list, press a button, read the KEY_ name and device name
```

**Not being detected?** `shutter_remote.py` retries device discovery every second (Bluetooth remotes routinely disconnect between presses to save battery, and may not even be connected yet when the app starts), so it should pick the remote up on its own within a second or two of it reconnecting. If it still doesn't, try power-cycling the remote — a stale/half-open Bluetooth connection from a previous session is a common cause and a fresh reconnect usually clears it.

**Was working, then stopped reconnecting entirely?** `shutter_remote.py` only watches for input devices the OS has already connected — it doesn't drive Bluetooth pairing/reconnection itself, so if `bluetoothd` stops auto-reconnecting to the remote, there's nothing for it to find no matter how long it retries. Check:
```bash
bluetoothctl devices          # find the remote's MAC address
bluetoothctl info <MAC>       # check Paired/Connected/Trusted
```
If `Paired: yes` but `Connected: no`, and `Trusted: no`, that's very likely the cause — an untrusted paired device doesn't get automatically reconnected by `bluetoothd` the same way a trusted one does, so once it disconnects (its normal power-saving behavior) it just stays disconnected until something explicitly reconnects it. Fix it with:
```bash
bluetoothctl trust <MAC>
```
which should make it reconnect immediately and keep auto-reconnecting from then on.

## Wired (USB Serial) Shutter Remote

For a simple homemade remote connected over USB serial and sending the word `click` (newline-terminated) each time its button is pressed. Implemented in [serial_shutter_remote.py](../serial_shutter_remote.py), it's much simpler than the Bluetooth remote above: one button, one action - it always takes a photo (the same event as the Bluetooth remote's `photo_key`), the same as pressing **Click** in Capture mode or, if you're currently in Play mode, switching back to Capture mode without taking a photo. It doesn't have a Speak/hold-to-talk equivalent.

To enable it:

1. Plug the remote in and find its device path: `ls /dev/ttyUSB* /dev/ttyACM*` (USB-serial adapters usually show up as one or the other, depending on the chip they use).
2. Set `"serial_remote"` in [settings.json](../settings.json.example):
   ```json
   "serial_remote": {
       "enabled": true,
       "port": "/dev/ttyUSB0",
       "baud_rate": 9600
   }
   ```
   `"baud_rate"` must match whatever the remote's firmware is actually configured to send at - 9600 is a common default, but check your specific device.
3. Make sure your user can access serial ports: `sudo usermod -aG dialout $USER`, then log out and back in (or reboot) for group membership to take effect.

This remote and the other two are fully independent - any combination can be `"enabled": true` at once, each triggering the same photo action.

**Not being detected / nothing happens on click?** Like the Bluetooth remote, `serial_shutter_remote.py` retries opening the port every second if it's missing (unplugged, not yet enumerated at boot), so it should pick the remote up within a second or two of being plugged in - check the console/log for a `SerialShutterRemote: listening on ...` line to confirm it connected. If it connects but clicks don't register, confirm what the remote is actually sending, e.g.:
```bash
screen /dev/ttyUSB0 9600
```
(press the remote's button and confirm you see `click` printed; `Ctrl-A` `k` `y` to exit `screen`) - a mismatched baud rate typically shows up as garbled text rather than silence.

## GPIO Shutter Remote

For a switch wired directly to a GPIO pin on the Pi - no microcontroller/USB adapter needed. Implemented in [gpio_shutter_remote.py](../gpio_shutter_remote.py) using [gpiozero](https://gpiozero.readthedocs.io/), which handles debouncing itself, so the wiring can be as simple as a switch between the GPIO pin and ground.

Like the serial remote, it's one button, one action - it always takes a photo, the same as pressing **Click** in Capture mode or, if you're currently in Play mode, switching back to Capture mode without taking a photo.

To enable it, set `"gpio_remote"` in [settings.json](../settings.json.example):
```json
"gpio_remote": {
    "enabled": true,
    "pin": 26,
    "active_low": true
}
```
* `"pin"` is the BCM GPIO number (not the physical header pin number) the switch is wired to.
* `"active_low"` should be `true` if the switch connects the pin to ground when pressed (the pin idles high via the Pi's internal pull-up resistor, and reads low when pressed) - this is the simplest wiring, needing nothing but a switch and two wires. Set it to `false` if the switch instead connects the pin to 3.3V when pressed (the pin idles low via the Pi's internal pull-down resistor, and reads high when pressed).

This remote and the other two are fully independent - any combination can be `"enabled": true` at once, each triggering the same photo action.

**Nothing happens on press?** Check the console/log for a `GpioShutterRemote: listening on GPIO<pin> (active low/high)` line at startup to confirm the pin opened - if it prints a "could not open" error instead, another process may already be using that pin, or the pin number may not exist on your Pi model. If it opened fine but presses don't register, double check `"active_low"` matches your wiring - a switch wired to ground with `"active_low": false` (or vice versa) will just look like the button is permanently held (or never pressed) rather than causing an obvious error.
