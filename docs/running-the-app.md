# Running the App

## From a Terminal

Once the virtual environment has been activated:

```bash
python custard_cream_camera.py
```

## From a Desktop Icon

[run_custard_cream_camera.sh](../run_custard_cream_camera.sh) and [custard-cream-camera.desktop](../custard-cream-camera.desktop) let you launch the app by double-clicking an icon instead of typing commands in a terminal. The script finds its own location automatically and activates `venv` if one exists next to it. `custard-cream-camera.desktop` ships with `Terminal=false`, so no terminal window appears — if `custard_cream_camera.py` exits with an error, the output goes to `custard_cream_camera.log` next to the script instead of a window you'd need a keyboard to dismiss. Set `Terminal=true` if you'd rather see a terminal window on launch (it will then keep it open on error so you can read what went wrong, instead of logging to a file).

To install it:

1. Edit `Exec=` in `custard-cream-camera.desktop` if this repo isn't cloned at `/home/rob/custard-cream-camera`.
2. Copy the `.desktop` file to your desktop and/or application menu:
   ```bash
   cp custard-cream-camera.desktop ~/Desktop/
   cp custard-cream-camera.desktop ~/.local/share/applications/   # to also show it in the app menu
   ```
3. Most file managers treat a newly-placed `.desktop` file as untrusted the first time — right-click the icon and choose "Allow Launching" / "Trust" (wording varies by desktop environment), or mark it executable if it isn't already:
   ```bash
   chmod +x ~/Desktop/custard-cream-camera.desktop
   ```
   On Raspberry Pi OS's default file manager, PCManFM, double-clicking instead pops up an "Execute / Execute in Terminal / Open / Cancel" menu every time, even once the file is executable - this isn't the same "untrusted" mechanism GNOME/Nautilus uses (so `gio set metadata::trusted` has no effect here), it's a PCManFM-only setting. Fix it via **File Manager → Edit → Preferences → General → "Don't ask options on launch executable file"**. This writes `quick_exec=1` to PCManFM's own config file - editing that file directly isn't a reliable alternative, since it may not exist yet until PCManFM has been opened/configured at least once. Note this is a global toggle: it suppresses the confirmation for any executable double-clicked on the desktop, not just this icon.

## What you'll see on launch

Depends on `settings.json`'s `"mode"` — see [Home Screen: Camera Mode vs FTP Mode](home-screen-modes.md):

* **Camera mode** — a live viewfinder with **Click**/**Play** buttons.
* **FTP mode** — no camera, so no viewfinder: it starts on a "Waiting for photos..." placeholder and switches to showing the newest received photo as soon as one arrives over FTP. See [Receiving Photos over FTP](ftp-setup.md) for configuring the camera side.

## A browser/keyring password dialog appears when the app closes

`custard_cream_camera.py` never opens a browser itself - if one appears (often along with a prompt to unlock/create a login keyring) right as the app exits, it's almost always a leftover browser window from the one-time `setup_flickr_auth.py` step (see [Publishing to Flickr](publishing-flickr.md)), still sitting open behind the fullscreen app the whole time it was running. Closing the app's fullscreen window just reveals what was underneath, it isn't spawning anything new.

Close the stray browser (`pkill chromium`, or whatever browser you used) to clear it. To stop it happening again:

* Run `setup_flickr_auth.py`'s browser step on a different device (phone, laptop) rather than this Pi's own desktop, and close that browser window once you've pasted the verification code back into the terminal.
* If you don't want passwords persisted on the Pi at all, turn off Chromium's password saving so it has nothing to ask the keyring to store: address bar → `chrome://settings/passwords` → toggle off **"Offer to save passwords"** (or via the **⋮** menu → Settings → Autofill and passwords → Password Manager if typing the URL doesn't work). You can also launch Chromium with `--password-store=basic` to bypass the OS keyring entirely.
