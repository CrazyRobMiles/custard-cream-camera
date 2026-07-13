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
