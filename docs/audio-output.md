# Audio Output (Shutter Sound)

Taking a photo (via the **Click** button, the [shutter remote](shutter-remote.md), or the spacebar) plays a short click sound in addition to the white screen flash, via `aplay`. This is implemented as a fire-and-forget call in `play_sound()` in [custard_cream_camera.py](../custard_cream_camera.py) - it never blocks on the sound finishing, and never raises if playback fails, so a missing or misconfigured audio device just means silence instead of a broken shutter button. This makes it safe to leave enabled even on a device with no audio hardware at all.

Configurable under `"audio_output"` in [settings.json](../settings.json.example):

```json
"audio_output": {
    "enabled": true,
    "device": null,
    "shutter_sound": "assets/audio/shutter.wav"
}
```

* `"enabled"` — set `false` to disable the sound entirely (the screen flash still happens either way).
* `"device"` — an explicit ALSA device string (e.g. `"plughw:3,0"`), passed to `aplay -D`. Leave `null` to use ALSA's `default` device.
* `"shutter_sound"` — path to a `.wav` file, relative to the repo root. The one shipped in [assets/audio/](../assets/audio/) is a short synthesized click generated with Python's stdlib `wave` module (not a real recording) - swap in your own `.wav` file here if you'd like a different sound.

## Finding the right output device

```bash
aplay -L
```
lists everything ALSA can currently see. On a plain HDMI/analog setup this is normally enough for `"device": null` to just work.

If you want to route through a Bluetooth speaker on modern Raspberry Pi OS (Bookworm and later), audio is managed by **PipeWire** + **WirePlumber**, not the ALSA `default` device directly - `wpctl status` will show the speaker under "Sinks" once paired and connected, even though it won't yet appear in `aplay -L`. `aplay` (a plain ALSA client) can only reach it once the ALSA→PipeWire bridge is installed:
```bash
sudo apt install pipewire-alsa
```
After that, `aplay -L` should show a `pipewire` entry, which either becomes the new ALSA default automatically or can be set explicitly via `"device": "pipewire"`.
