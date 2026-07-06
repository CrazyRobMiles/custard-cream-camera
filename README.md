
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