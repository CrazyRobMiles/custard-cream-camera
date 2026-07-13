# Running the App

## From a Terminal

Once the virtual environment has been activated:

```bash
python magic_camera.py
```

## From a Desktop Icon

[run_magic_camera.sh](../run_magic_camera.sh) and [magic-camera.desktop](../magic-camera.desktop) let you launch the app by double-clicking an icon instead of typing commands in a terminal. The script finds its own location automatically and activates `venv` if one exists next to it. `magic-camera.desktop` ships with `Terminal=false`, so no terminal window appears — if `magic_camera.py` exits with an error, the output goes to `magic_camera.log` next to the script instead of a window you'd need a keyboard to dismiss. Set `Terminal=true` if you'd rather see a terminal window on launch (it will then keep it open on error so you can read what went wrong, instead of logging to a file).

To install it:

1. Edit `Exec=` in `magic-camera.desktop` if this repo isn't cloned at `/home/rob/custard-cream-camera`.
2. Copy the `.desktop` file to your desktop and/or application menu:
   ```bash
   cp magic-camera.desktop ~/Desktop/
   cp magic-camera.desktop ~/.local/share/applications/   # to also show it in the app menu
   ```
3. Most file managers treat a newly-placed `.desktop` file as untrusted the first time — right-click the icon and choose "Allow Launching" / "Trust" (wording varies by desktop environment), or mark it executable if it isn't already:
   ```bash
   chmod +x ~/Desktop/magic-camera.desktop
   ```
