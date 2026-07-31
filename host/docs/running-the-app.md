# Running the App

## From a Terminal

Once the virtual environment has been activated:

```bash
python custard_cream_camera_host.py
```

## From a Desktop Icon

[run_custard_cream_camera_host.sh](../run_custard_cream_camera_host.sh) and [custard-cream-camera-host.desktop](../custard-cream-camera-host.desktop) let you launch the app by double-clicking an icon instead of typing commands in a terminal. The script finds its own location automatically and activates `venv` if one exists next to it. `custard-cream-camera-host.desktop` ships with `Terminal=false`, so no terminal window appears — if `custard_cream_camera_host.py` exits with an error, the output goes to `custard_cream_camera_host.log` next to the script instead of a window you'd need a keyboard to dismiss. Set `Terminal=true` if you'd rather see a terminal window on launch (it will then keep it open on error so you can read what went wrong, instead of logging to a file).

To install it:

1. Edit `Exec=` in `custard-cream-camera-host.desktop` if this repo isn't cloned at `/home/rob/custard-cream-camera`.
2. Copy the `.desktop` file to your desktop and/or application menu:
   ```bash
   cp custard-cream-camera-host.desktop ~/Desktop/
   cp custard-cream-camera-host.desktop ~/.local/share/applications/   # to also show it in the app menu
   ```
3. Most file managers treat a newly-placed `.desktop` file as untrusted the first time — right-click the icon and choose "Allow Launching" / "Trust" (wording varies by desktop environment), or mark it executable if it isn't already:
   ```bash
   chmod +x ~/Desktop/custard-cream-camera-host.desktop
   ```
   On Raspberry Pi OS's default file manager, PCManFM, double-clicking instead pops up an "Execute / Execute in Terminal / Open / Cancel" menu every time, even once the file is executable - see [Camera app: Running the App](../../camera/docs/running-the-app.md#from-a-desktop-icon) for the fix (same PCManFM setting, not specific to either app).

## What you'll see on launch

There's no live viewfinder in this app — it starts on a "Waiting for photos..." placeholder and switches to showing the newest received photo as soon as the first one arrives over FTP. See [Receiving Photos over FTP](ftp-setup.md) for configuring the camera side, and [Reviewing Received Photos](reviewing-photos.md) for what you can do with them once they arrive.
