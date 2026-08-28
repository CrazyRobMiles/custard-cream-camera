# Receiving Photos over FTP

The Sony A7R IV can upload JPEGs (optionally alongside RAW) to an FTP server automatically after each shot, or on demand for selected images, via its built-in FTP-transfer feature. This app runs that FTP server - [lib/ftp_server.py](../lib/ftp_server.py), built on [pyftpdlib](https://pyftpdlib.readthedocs.io/) - whenever `settings.json`'s `"mode"` is `"ftp"` or `"camera_ftp"`, and shows each upload as it arrives, using the same review/print/publish/voice-edit flow as camera mode's Play mode (see [Home Screen: Camera Mode vs FTP Mode](home-screen-modes.md)).

## Configuring the app

The `"ftp"` block in [settings.json](../settings.json.example):

```json
"ftp": {
    "host": "0.0.0.0",
    "port": 2121,
    "username": "sony",
    "password": "changeme",
    "incoming_dir": "ftp_incoming"
}
```

* `"host"` — the address to listen on. `0.0.0.0` (the default) listens on every network interface this device has; narrow it to a specific address if you want the server reachable only over one of them (e.g. a dedicated Wi-Fi network shared with the camera).
* `"port"` — deliberately **not** the standard FTP port 21: binding a port below 1024 needs root (or a `setcap` grant) on Linux, which this app doesn't ask for. Use whatever custom port you set here as the camera's FTP server port too - both sides just need to agree.
* `"username"`/`"password"` — change these from the shipped defaults. This is a plain-auth FTP server with no TLS by default; treat it as trusted-LAN-only (see [Security notes](#security-notes) below), not something to expose to the open internet.
* `"incoming_dir"` — a scratch folder (relative to this app's own directory, gitignored) the camera's FTP session actually writes into. You never need to look in here directly - see [How uploads get flattened](#how-uploads-get-flattened-into-captures).

## Configuring the camera

Exact menu wording varies by firmware version, so treat this as a guide rather than an exact click-by-click script - consult Sony's current manual for your firmware if a step doesn't match what you see:

1. On the camera, go to the network/FTP transfer settings (under the Network menu on recent firmware) and set up an FTP connection: server address/hostname = this device's IP address on your shared network, port = whatever you set `"ftp"."port"` to above (not 21), username/password = whatever you set above.
2. Set the connection method to **Wired LAN**, **Wi-Fi**, or via a smartphone/USB tether, depending on how this device and the camera are actually networked - they need to be able to reach each other, e.g. both on the same Wi-Fi network, or connected directly via the camera's Wi-Fi access-point mode.
3. Set **FTP Transfer** (or **Auto Transfer during REC** / equivalent for your firmware) to on, and choose whether it uploads every shot automatically or only images you mark for transfer during playback - either works fine with this app, since it just reacts to whatever arrives.
4. Leave the camera's own "target folder" / date-folder option at whatever default it offers - it doesn't matter which folder structure the camera creates on the server, see below.

## How uploads get flattened into `captures/`

Sony's FTP client may create a dated subfolder (e.g. `2026_07_28`) under the server root and upload into that, depending on camera settings and firmware - this app doesn't rely on any particular behavior here. `ftp_server.py`'s `on_file_received()` callback fires once a file finishes uploading, wherever under `incoming_dir` it landed, and:

1. Ignores it (leaving it in place, untouched) if it's not a `.jpg`/`.jpeg` file - e.g. a RAW `.ARW` file from simultaneous RAW+JPEG capture is stored but never previewed.
2. Otherwise moves it into `captures/` (flat, no subfolders) with a lower-cased `.jpg` extension - cameras write e.g. `DSC01234.JPG`, and the shared review code globs `*.jpg`, which is case-sensitive on Linux; without lower-casing, uploaded photos would silently never appear.
3. Renames on collision (`_2`, `_3`, ...) rather than overwriting, in the rare case two uploads produce the same filename (e.g. after the camera's internal file counter wraps around).

The photo then becomes the current selection on screen immediately - see [When a new photo arrives](home-screen-modes.md#when-a-new-photo-arrives).

## Testing without a camera

Any FTP client can stand in for the camera while testing:

```bash
curl -T some_photo.jpg "ftp://sony:changeme@<this-device-ip>:2121/"
```

If that shows up on screen, the camera side is just a matter of getting its FTP settings to match.

## Security notes

This FTP server accepts plain-text username/password auth with no encryption, and grants the configured user just enough permission to list, create a subfolder, and write files (`elmw` - see `ftp_server.py`) - no read-back or delete. That's appropriate for a device on a private/trusted network talking only to your own camera, but:

* Don't forward this port through your router to the public internet.
* Change the default `"username"`/`"password"` in `settings.json` before relying on this.
* If the camera and this device share Wi-Fi with other devices you don't fully trust, consider the camera's own Wi-Fi access-point mode (a direct camera-to-device connection) instead of a shared network.
