# Capture Mode and Play Mode

The app has two modes:

## Capture mode

The default mode: a live viewfinder with **Click** (take a photo) and **Play** (switch to Play mode) buttons, plus the [exposure compensation](exposure-compensation.md) EV-/EV+ buttons in the top corners.

## Play mode

Reviews and acts on photos already in `captures/`, one at a time, full screen:

* **Capture** — back to Capture mode (the live viewfinder), without taking a photo.
* **Print** / **Speak** / **Publish** — act immediately on whichever photo is currently shown, no separate "choose, then act" step. **Speak** is hold-to-talk: press to record an editing instruction, release to send it, exactly like Capture mode's old Speak button but targeting the photo on screen instead of a fresh capture. See [Voice-Prompted AI Edits](voice-ai-edits.md), [Printing](printing.md), and [Publishing to Flickr](publishing-flickr.md) for what each of those actually does.
* **`<`** / **`>`** (small buttons on the left/right screen edges) — step to the previous/next photo one at a time, newest-first.
* **Page** (top-right corner) — opens a 3×3 grid of the current page of 9 photos; tapping a thumbnail makes it the current selection and returns to the single-photo view. **Left**/**Right** in the grid page through older/newer groups of 9; **Back** returns to the single-photo view without changing the selection.

Entering Play mode (via the **Play** button, from anywhere) always lands on the most recently taken photo - it re-scans `captures/` fresh each time rather than remembering a stale position from last visit. An AI edit or a fresh **Click** while reviewing similarly become the new current selection, the same as if you'd just taken them.

There's no on-screen quit button in either mode — press keyboard `q` in the terminal, or (on the HDMI backends) Escape / close the window.

## The physical shutter remote and keyboard spacebar

The [Bluetooth shutter remote](shutter-remote.md)'s photo key and the keyboard spacebar behave differently depending on mode:

* In **Capture mode**, they take a photo immediately, same as **Click**.
* In **Play mode**, they switch back to Capture mode *without* taking a photo — pressing the physical shutter while reviewing old photos shouldn't blindly capture whatever the camera happens to be pointed at; it just gets you back to the viewfinder to compose deliberately.

The remote's speak key is unaffected by mode — it always bypasses Play mode entirely and acts immediately on a fresh capture, since requiring on-screen navigation would defeat the point of a physical, look-free trigger.
