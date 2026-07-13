# Bluetooth Shutter Remote

Cheap Bluetooth camera remotes don't have a real "pairing mode" — they just have two buttons/positions (labelled iOS/Android or similar) that each send a different key, since iOS and Android camera apps historically listened for different shortcuts. [shutter_remote.py](../shutter_remote.py) listens for both directly at the input-device level (via `evdev`), independent of which window has focus:

* **iOS** button → Volume Up (`KEY_VOLUMEUP`) → takes a photo, the same action as the **Click** button.
* **Android** button → Enter (`KEY_ENTER`) → hold-to-talk, the same as the **Speak** button: pressing starts recording, releasing sends it. This relies on the remote sending a genuine press-then-release pair for a physical hold, which is normal HID keyboard behavior, but worth confirming for your specific unit (see below).

To enable it:

1. Set `"shutter_remote": {"enabled": true}` in [settings.json](../settings.json).
2. Make sure your user can read input devices: `sudo usermod -aG input $USER`, then log out and back in (or reboot) for group membership to take effect.

The Volume Up mapping is easy to confirm: pressing the iOS button should show your desktop's volume OSD. The Enter mapping is a best guess for "Android mode" on these remotes — if it doesn't trigger recording, confirm the actual key it sends (see below), and set `"photo_key"`/`"speak_key"` in `settings.json` to match (either can be set to `null` to disable that mapping without disabling the other).

## Automatic device discovery

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

**Not being detected?** `shutter_remote.py` retries device discovery every few seconds (Bluetooth remotes routinely disconnect between presses to save battery, and may not even be connected yet when the app starts), so it should pick the remote up on its own within a few seconds of it reconnecting. If it still doesn't, try power-cycling the remote — a stale/half-open Bluetooth connection from a previous session is a common cause and a fresh reconnect usually clears it.
