# Image Browser

Pressing **Speak**, **Print**, or **Publish** opens an image browser rather than acting immediately, so you can choose *which* photo to edit, print, or publish instead of always using the last one taken:

1. A 3×3 grid of the 9 most recent photos in `captures/` appears (newest first), with **Left**/**Right** to page through older ones and **Quit** to cancel and go back to the live viewfinder.
2. Tapping a thumbnail shows it fullscreen with **Select**/**Ignore** buttons. **Ignore** goes back to the grid; **Select** proceeds with whichever action (Speak, Print, or Publish) opened the browser, using that image.
3. For **Print** and **Publish**, Select immediately acts on the chosen image. For **Speak**, Select becomes a hold-to-talk button — press to record, release to send, exactly like the original Speak button, just targeting the chosen photo instead of a fresh capture.

This only applies to the on-screen Speak/Print/Publish buttons. The [Bluetooth shutter remote](shutter-remote.md)'s photo/speak keys deliberately bypass the browser and act immediately on a fresh capture, since requiring on-screen navigation would defeat the point of a physical, look-free trigger.

There's no on-screen quit button — press keyboard `q` in the terminal, or (on the HDMI backends) Escape / close the window.
