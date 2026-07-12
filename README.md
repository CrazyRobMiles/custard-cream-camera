
# Nanobanana Camera

A homage to the one made by [Nikbuild](https://github.com/nickbild/banamera)

This repository provides a small Python app that captures video from the
Raspberry Pi HQ Camera using `picamera2` and displays it on an LCD panel. You can then use AI prompts to edit the picture using Nanobanana. 

# Setting Up the Python Virtual Environment on Raspberry Pi OS

This project always runs inside a Python virtual environment — everything below happens in a `venv`, nothing is installed into the system Python. The only wrinkle on a Raspberry Pi is `picamera2`.

## Why Use `--system-site-packages`?

Almost every dependency (`pillow`, `numpy`, `spidev`, `RPi.GPIO`, `pygame`) is a normal PyPI package and installs fine into any plain venv via `requirements.txt` — no apt packages needed for those.

`picamera2` is the one exception. It's built on top of `libcamera`, which talks directly to the Pi's camera ISP and tuning files, and is not published as a portable pip wheel — it has to be the OS build from `apt` so it matches your kernel and camera stack. A plain (isolated) venv can't see that OS-installed package, so we create the venv with `--system-site-packages`: this lets the venv see the apt-installed `picamera2`/`libcamera`, while every other package still installs normally and independently via `pip`.

## Installing System Packages

Install `picamera2` and its `libcamera` dependency (Raspberry Pi OS / Debian-like):

```bash
sudo apt update
sudo apt install -y \
	python3-picamera2 \
	python3-libcamera \
	python3-venv
```

## Creating the Virtual Environment

From the root of the repository:

```bash
python3 -m venv --system-site-packages venv
```

This creates a virtual environment in the `venv` folder.

## Activating the Virtual Environment

```bash
source venv/bin/activate
```

The command prompt should change to show that the virtual environment is active:

```text
(venv) rob@raspberrypi:~/my-project $
```

## Installing Python Dependencies

Install the packages listed in `requirements.txt`:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

These packages are installed into the virtual environment and do not affect the system Python installation.

## Verifying Camera Support

To check that the virtual environment can access the Raspberry Pi camera libraries:

```bash
python -c "from picamera2 import Picamera2; print('Picamera2 OK')"
```

and:

```bash
python -c "import libcamera; print('libcamera OK')"
```

# Using a Canon SELPHY CP400 with Raspberry Pi and CUPS

A good way to get cheap hard copy connect a Canon SELPHY CP400 dye-sublimation photo printer your a Raspberry Pi.

## Hardware Used

* Raspberry Pi (tested on Raspberry Pi 5)
* Canon SELPHY CP400
* Canon KP-36IP postcard media pack
* USB connection between printer and Pi

## Add Your User to the Printer Administration Group

Installations and printer management require membership of the `lpadmin` group.

```bash
sudo usermod -aG lpadmin $USER
```

Log out and back in after running this command.

Verify membership:

```bash
groups
```

You should see `lpadmin` in the list.

## Install CUPS

Install the CUPS printing system:

```bash
sudo apt update
sudo apt install cups
```

Enable and start CUPS:

```bash
sudo systemctl enable cups
sudo systemctl start cups
```

Check that it is running:

```bash
systemctl status cups
```

## Install Gutenprint

The Raspberry Pi package repository contains a Gutenprint package:

```bash
sudo apt install printer-driver-gutenprint
```

Unfortunately, the packaged version may contain a bug that prevents the CP400 from recognising postcard media correctly.

Typical error:

```text
Incorrect paper loaded (01 vs 11), aborting job!
```

If you encounter this error, build Gutenprint from source as described below.

## Building Gutenprint from Source

Install build dependencies:

```bash
sudo apt install \
    build-essential \
    libcups2-dev \
    libcupsimage2-dev \
    libusb-1.0-0-dev \
    libtiff-dev \
    libjpeg-dev \
    libpng-dev \
    gettext
```

Download and unpack Gutenprint:

```bash
wget https://downloads.sourceforge.net/project/gimp-print/gutenprint-5.3/5.3.3/gutenprint-5.3.3.tar.xz

tar xf gutenprint-5.3.3.tar.xz

cd gutenprint-5.3.3
```

Build and install:

```bash
./configure
make -j4
sudo make install
```

Restart CUPS:

```bash
sudo systemctl restart cups
```

## Discover the Printer

Connect the CP400 via USB and run:

```bash
lpinfo -v
```

Typical output:

```text
direct gutenprint53+usb://canon-cp400/NONE_UNKNOWN
```

Find the available driver:

```bash
lpinfo -m | grep -i cp400
```

Typical output:

```text
gutenprint.5.3://canon-cp400/expert Canon SELPHY CP400
```

## Create the Printer

Create the printer using the discovered URI and driver:

```bash
sudo lpadmin \
    -p SELPHY_CP400 \
    -E \
    -v "gutenprint53+usb://canon-cp400/NONE_UNKNOWN" \
    -m "gutenprint.5.3://canon-cp400/expert"
```

Enable the printer:

```bash
sudo cupsenable SELPHY_CP400
sudo cupsaccept SELPHY_CP400
```

Make it the default printer:

```bash
sudo lpadmin -d SELPHY_CP400
```

## Verify Page Size

Check available page sizes:

```bash
lpoptions -p SELPHY_CP400 -l | grep PageSize
```

Expected output:

```text
PageSize/Media Size: *Postcard w253h337 w155h244 w283h566
```

The asterisk indicates the current default.

The CP400 should normally use:

```text
Postcard
```

when printing KP-36IP media.

## Paper Size Problems

If printing fails with:

```text
Incorrect paper loaded (01 vs 11), aborting job!
```

check the following:

### 1. Correct Media Pack

Use matching Canon paper and ribbon cartridges.

Example:

```text
KP-36IP
```

### 2. Correct Cassette

Ensure the cassette is marked:

```text
Postcard
```

and matches the media pack.

### 3. Correct Driver Page Size

Verify:

```bash
lpoptions -p SELPHY_CP400 -l | grep PageSize
```

shows:

```text
*Postcard
```

### 4. Rebuild Gutenprint

If all settings are correct and the error persists, rebuild Gutenprint from source.

In testing, rebuilding Gutenprint resolved the "01 vs 11" media mismatch problem.

## Print a Test Page

Print the CUPS test page:

```bash
lp -d SELPHY_CP400 /usr/share/cups/data/testprint
```

If successful, the printer should begin feeding paper and printing immediately.

## Useful Commands

Show printer status:

```bash
lpstat -p -d
```

Show printer options:

```bash
lpoptions -p SELPHY_CP400
```

Show printer configuration:

```bash
lpstat -l -p SELPHY_CP400
```

Show recent CUPS errors:

```bash
tail -50 /var/log/cups/error_log
```

Both commands should complete without errors. Enable the camera stack (libcamera) in `raspi-config` if needed.


## Running the Application

Once the virtual environment has been activated:

```bash
python magic_camera.py
```

## Camera Orientation

If the live viewfinder (or captured photos) comes out flipped or upside down - typically because the HQ camera sensor ended up mounted rotated in the enclosure - correct it with `"hflip"`/`"vflip"` under `"camera"` in [settings.json](settings.json), rather than physically remounting the sensor or rotating images in software after the fact:

```json
"camera": {
    "hflip": true,
    "vflip": true
}
```

Both `true` (the default in this repo's `settings.json`) corrects a sensor mounted rotated 180 degrees; use just one of the two if your image is mirrored on a single axis instead. This is applied once, in the camera's own capture pipeline via `libcamera`'s `Transform`, so it covers the viewfinder, saved photos, and whatever gets sent off for AI editing - not something each part of the app has to individually work around.

## Display backends

`magic_camera.py` renders through a pluggable display layer in [displays/](displays/). Three backends are provided:

* `ili9486` — the SPI ILI9486 LCD + XPT2046 touch panel ([displays/ili9486_display.py](displays/ili9486_display.py))
* `hdmi-desktop` — a plain window via Tkinter, using the mouse for touch input ([displays/hdmi_desktop_display.py](displays/hdmi_desktop_display.py)). No fullscreen mode-switching or video driver selection — it just opens an ordinary window through whatever windowing system the desktop is already using, the same as any other desktop app. This is the simplest option and the one to try first on a device with a native HDMI display.
* `hdmi-pygame` — a dedicated fullscreen SDL/pygame surface, using the mouse for touch input ([displays/hdmi_pygame_display.py](displays/hdmi_pygame_display.py)). Bypasses the desktop's window manager for lower-overhead fullscreen updates, at the cost of needing a working SDL video driver for your setup — reach for this only if `hdmi-desktop`'s performance isn't enough.

Select the backend and tune its options in [settings.json](settings.json):

```json
{
    "display": {
        "type": "ili9486"
    }
}
```

Set `"type"` to `"hdmi-desktop"` or `"hdmi-pygame"` to run on a device with a native HDMI display instead. `hdmi-desktop` needs Tkinter, which on Raspberry Pi OS / Debian is a system package, not a pip one:

```bash
sudo apt install python3-tk
```

### `DISPLAY`/`XDG_RUNTIME_DIR` not set

Both HDMI backends need `DISPLAY` (and ideally `XDG_RUNTIME_DIR`) set to reach the desktop session — normally automatic when logged into the Pi's own desktop, but **not** when launched from a plain SSH shell or a remote-dev tool's integrated terminal (e.g. VS Code Remote-SSH), which don't inherit those variables. Activating the Python venv doesn't set them either (it only touches `PATH`), so this can bite regardless of venv use.

`displays/__init__.py` fills in a best-effort default for either one if it's missing — it looks for a real X11 socket under `/tmp/.X11-unix` and a real `/run/user/<uid>` directory, and only sets the variable if it finds one (it won't invent a display that doesn't actually exist), printing what it defaulted to. This should cover the common case of a single desktop session on `:0` without you needing to `export` anything by hand. If it still can't find one — e.g. no desktop session is running at all — the underlying error will still surface, since at that point there's genuinely nothing to connect to.

## Running from a Desktop Icon

[run_magic_camera.sh](run_magic_camera.sh) and [magic-camera.desktop](magic-camera.desktop) let you launch the app by double-clicking an icon instead of typing commands in a terminal. The script finds its own location automatically, activates `venv` if one exists next to it, and (if `magic_camera.py` exits with an error) keeps the terminal window open so you can read what went wrong instead of it just vanishing.

To install it:

1. Edit `Exec=` in `magic-camera.desktop` if this repo isn't cloned at `/home/rob/nanobanana-camera`.
2. Copy the `.desktop` file to your desktop and/or application menu:
   ```bash
   cp magic-camera.desktop ~/Desktop/
   cp magic-camera.desktop ~/.local/share/applications/   # to also show it in the app menu
   ```
3. Most file managers treat a newly-placed `.desktop` file as untrusted the first time — right-click the icon and choose "Allow Launching" / "Trust" (wording varies by desktop environment), or mark it executable if it isn't already:
   ```bash
   chmod +x ~/Desktop/magic-camera.desktop
   ```

## Image Browser

Pressing **Speak**, **Print**, or **Publish** opens an image browser rather than acting immediately, so you can choose *which* photo to edit, print, or publish instead of always using the last one taken:

1. A 3×3 grid of the 9 most recent photos in `captures/` appears (newest first), with **Left**/**Right** to page through older ones and **Quit** to cancel and go back to the live viewfinder.
2. Tapping a thumbnail shows it fullscreen with **Select**/**Ignore** buttons. **Ignore** goes back to the grid; **Select** proceeds with whichever action (Speak, Print, or Publish) opened the browser, using that image.
3. For **Print** and **Publish**, Select immediately acts on the chosen image. For **Speak**, Select becomes a hold-to-talk button — press to record, release to send, exactly like the original Speak button, just targeting the chosen photo instead of a fresh capture.

This only applies to the on-screen Speak/Print/Publish buttons. The [Bluetooth shutter remote](#bluetooth-shutter-remote)'s photo/speak keys deliberately bypass the browser and act immediately on a fresh capture, since requiring on-screen navigation would defeat the point of a physical, look-free trigger.

There's no on-screen quit button — press keyboard `q` in the terminal, or (on the HDMI backends) Escape / close the window.

## Voice-Prompted AI Edits

Choose a photo via the image browser (or use the shutter remote's speak key) and hold **Select** (or the remote button), say an editing instruction (e.g. "make it look like a watercolor painting"), and release — the app transcribes what you said and sends it with the chosen image to Google's Gemini ("Nano Banana") image model for editing. The result is saved to `captures/` as `ai_<timestamp>.jpg` and shown on screen for a few seconds. This is implemented in [nanobanana.py](nanobanana.py); the viewfinder and Stop button stay responsive while it's working since the network calls run on a background thread.

Requirements:

* A microphone, and `arecord` available (part of `alsa-utils`, normally already installed on Raspberry Pi OS — `sudo apt install alsa-utils` if not).
* A Gemini API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey), set as an environment variable **before launching the app** (not stored in `settings.json`, since that file is checked into git):
  ```bash
  export GOOGLE_API_KEY="your-api-key"
  ```
  If launching from a desktop icon, add the `export` line to `~/.bashrc` (or wherever your shell profile lives) so it's set before `run_magic_camera.sh` runs.

Model names, recording length, and the result's on-screen hold time are all configurable under `"nanobanana"` in [settings.json](settings.json). The model IDs (`transcribe_model`, `edit_model`) may need adjusting as Google's model naming evolves — check the current names in the [Gemini API docs](https://ai.google.dev/gemini-api/docs/models) if editing fails with a "model not found" style error.

## Printing

The **Print** button (via the image browser) sends the chosen photo to CUPS (`lp <file>`) — see the [Canon SELPHY CP400 setup](#using-a-canon-selphy-cp400-with-raspberry-pi-and-cups) above for getting a printer configured. `lp` only queues the job; if the printer is offline, out of paper, etc., that failure shows up in CUPS (`lpstat`, its web UI, or `/var/log/cups/error_log`) rather than in `magic_camera.py`.

By default `lp` is called with no `-d` flag, meaning it uses CUPS's configured default destination — if you get `lp: Error - No default destination`, either set one with `sudo lpadmin -d <printer-name>` (see `lpstat -p -d` for the list of configured printers and current default), or set `"printer": "<printer-name>"` under `"printing"` in [settings.json](settings.json) to have the app always target that printer explicitly, independent of the system default.

### Print Testing

Set `"test_mode": true` under `"printing"` in [settings.json](settings.json) to try out the print pipeline — watermark and date stamp included — without spending paper/ink: pressing **Print** saves the exact image that would have been sent to `lp` into `"test_folder"` (default `print_tests/`, gitignored) instead of actually printing it. The console prints exactly where it was saved. Set back to `false` (the default) to resume printing for real.

### Watermark and Date Stamp

Prints can have a watermark logo and/or a date/time stamp composited on automatically — implemented in [print_overlays.py](print_overlays.py). Both are applied only to the copy sent to the printer (via a temporary file); the original saved photo in `captures/` is never modified.

**Watermark** (`"watermark"` in [settings.json](settings.json)):

```json
"watermark": {
    "enabled": true,
    "file": "assets/images/watermark.png",
    "horizontal_align": "right",
    "vertical_align": "bottom",
    "width_fraction": 0.2,
    "margin_fraction": 0.02
}
```

* `"file"` — path to a PNG, relative to the repo root. Transparent areas show the photo through, so the source PNG needs an alpha channel (both files under [assets/images/](assets/images/) already have one).
* `"horizontal_align"`/`"vertical_align"` — which corner: `"left"`/`"right"` and `"top"`/`"bottom"`.
* `"width_fraction"` — how wide the watermark should be, as a fraction of the photo's width (aspect ratio is preserved, so this also determines its height).
* `"margin_fraction"` — gap from the edges, as a fraction of the photo's width/height.

**Date stamp** (`"datestamp"` in settings.json):

```json
"datestamp": {
    "enabled": true,
    "format": "%Y-%m-%d %H:%M",
    "horizontal_align": "left",
    "vertical_align": "bottom",
    "font_fraction": 0.035,
    "margin_fraction": 0.02,
    "text_colour": [255, 255, 255, 255],
    "background_colour": [0, 0, 0, 140]
}
```

* `"format"` — a [`strftime`](https://docs.python.org/3/library/time.html#time.strftime) format string. The stamp reflects when the photo was actually taken (the file's modification time), not when it's printed.
* `"font_fraction"` — text size as a fraction of the photo's height.
* `"text_colour"`/`"background_colour"` — `[R, G, B, A]`; the background box (drawn behind the text for legibility over busy photos) defaults to semi-transparent black.

Both default to the bottom corners (watermark bottom-right, date stamp bottom-left) so they don't overlap — adjust either independently if you'd rather they sit elsewhere. If a watermark/date stamp fails to apply for any reason (bad path, corrupt font, etc.), that step is skipped with a printed error rather than blocking the print entirely.

## Bluetooth Shutter Remote

Cheap Bluetooth camera remotes don't have a real "pairing mode" — they just have two buttons/positions (labelled iOS/Android or similar) that each send a different key, since iOS and Android camera apps historically listened for different shortcuts. [shutter_remote.py](shutter_remote.py) listens for both directly at the input-device level (via `evdev`), independent of which window has focus:

* **iOS** button → Volume Up (`KEY_VOLUMEUP`) → takes a photo, the same action as the **Click** button.
* **Android** button → Enter (`KEY_ENTER`) → hold-to-talk, the same as the **Speak** button: pressing starts recording, releasing sends it. This relies on the remote sending a genuine press-then-release pair for a physical hold, which is normal HID keyboard behavior, but worth confirming for your specific unit (see below).

To enable it:

1. Set `"shutter_remote": {"enabled": true}` in [settings.json](settings.json).
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

**Not being detected?** `shutter_remote.py` retries device discovery every few seconds (Bluetooth remotes routinely disconnect between presses to save battery, and may not even be connected yet when the app starts), so it should pick the remote up on its own within a few seconds of it reconnecting. If it still doesn't, try power-cycling the remote — a stale/half-open Bluetooth connection from a previous session is a common cause and a fresh reconnect usually clears it.

## Publishing to Flickr

The **Publish** button (via the [image browser](#image-browser)) uploads the chosen photo to Flickr, tagged with whatever's configured in `settings.json`. This is built as a pluggable layer in [publishers/](publishers/) — the same shape as [displays/](displays/) — so other services (Instagram, a self-hosted gallery, whatever) could be added later as siblings to `flickr_publisher.py` without touching `magic_camera.py` beyond a new `"type"` branch in `publishers/__init__.py`.

### One-time setup

Flickr uses OAuth 1.0a, which needs a real browser to authorize the app — but only **once**. This is deliberately kept separate from the main camera app:

1. Get an API key and secret from [flickr.com/services/apps/create](https://www.flickr.com/services/apps/create/) (needs your Pro account login).
2. Set them as environment variables (same reasoning as the Gemini API key — never stored in `settings.json`, which is checked into git):
   ```bash
   export FLICKR_API_KEY="your-api-key"
   export FLICKR_API_SECRET="your-api-secret"
   ```
3. Run the one-time setup script:
   ```bash
   python setup_flickr_auth.py
   ```
   It prints a URL — open it in a browser on *any* device (your phone is fine, it doesn't have to be the Pi), log into Flickr, authorize the app, and paste the verification code it gives you back into the terminal. This caches an access token locally (via `flickrapi`'s own cache, typically `~/.flickr/`).

After that, **Publish** works with no further browser interaction — `magic_camera.py` only ever does the upload itself, using the cached token. If it's ever missing or expired, publishing fails with a clear message pointing back at this script rather than trying to prompt interactively (there's no browser available from a background upload thread).

If launching from a desktop icon, add the two `export` lines to `~/.bashrc` so they're set before `run_magic_camera.sh` runs — same as the Gemini API key.

### Configuration

```json
"publish": {
    "type": "flickr",
    "flickr": {
        "api_key_env": "FLICKR_API_KEY",
        "api_secret_env": "FLICKR_API_SECRET",
        "tags": "nanobananacamera",
        "is_public": true,
        "token_cache_dir": null
    }
}
```

* `"tags"` — space-separated tags applied to every upload; multi-word tags need their own quotes inside the string, e.g. `"tags": "nanobananacamera \"family holiday\""`.
* `"is_public"` — `true` posts immediately visible to anyone on Flickr; set `false` for private (only you) instead.
* `"token_cache_dir"` — leave `null` to use `flickrapi`'s own default cache location; only set this if you need the token stored somewhere specific.

Publishing runs on a background thread, the same way the AI edit does, so the viewfinder and other buttons stay responsive during the upload.

## Deactivating the Virtual Environment

When you have finished working:

```bash
deactivate
```

This returns you to the system Python environment.

## Recreating the Environment

If the environment becomes corrupted or you want to start again:

```bash
deactivate
rm -rf venv

python3 -m venv --system-site-packages venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

## Notes

* Do not commit the `venv` folder to Git.
* Add `venv/` to `.gitignore`.
* The `requirements.txt` file should contain only packages installed via `pip`.
* Raspberry Pi OS packages such as Picamera2 should be installed using `apt`, not added to `requirements.txt`.