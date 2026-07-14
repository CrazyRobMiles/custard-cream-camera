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
