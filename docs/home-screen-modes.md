# Home Screen: Camera Mode vs FTP Mode

`settings.json`'s top-level `"mode"` key (`"camera"`, `"ftp"`, or `"camera_ftp"`) picks which home
screen this app shows. Everything else — reviewing, printing, publishing, and voice-editing photos
already in `captures/` — works identically across all three; only how photos *arrive* differs.

## Camera mode (`"mode": "camera"`)

Live viewfinder with a **Capture** and **Play** mode.

### Capture mode

The default mode: a live viewfinder with **Click** (take a photo) and **Play** (switch to Play
mode) buttons, plus the [exposure compensation](exposure-compensation.md) EV-/EV+ buttons in the
top corners.

### Play mode

Reviews and acts on photos already in `captures/`, one at a time, full screen:

* **Capture** — back to Capture mode (the live viewfinder), without taking a photo.
* **Print** / **Speak or AI Edit** / **Publish** — act immediately on whichever photo is currently
  shown, no separate "choose, then act" step. The AI-edit button's behavior depends on
  `"ai_edit"` in settings.json: by default (`"input_method": "voice"`) it's **Speak**, hold-to-talk
  — press to record an editing instruction, release to send it; with `"input_method": "keyboard"`
  it's **AI Edit**, a normal tap that opens a grid of preset prompts plus a custom on-screen-keyboard
  option instead. Setting `"ai_edit.enabled"` to `false` removes this button entirely. **Publish**
  opens a menu of every *enabled* destination (Flickr, Bluesky, Custard Cream Server, ...) — tap one
  to send this photo there and return here, with a "Published to \<name\>!" confirmation naming
  which one; publishing to more than one destination means pressing **Publish** again afterwards and
  picking another. If only one destination is enabled, Publish skips the menu and sends straight to
  it. See [Voice-Prompted AI Edits](voice-ai-edits.md), [Printing](printing.md), and
  [Publishing to Flickr](publishing-flickr.md) for what each of those actually does.
* **`<`** / **`>`** (small buttons on the left/right screen edges) — step to the previous/next
  photo one at a time, newest-first.
* **Page** (top-right corner) — opens a 3×3 grid of the current page of 9 photos; tapping a
  thumbnail makes it the current selection and returns to the single-photo view. **Left**/**Right**
  in the grid page through older/newer groups of 9; **Back** returns to the single-photo view
  without changing the selection.
* **Stop** (top-left corner) — exits the app cleanly. This is the only on-screen way to quit, for
  when it's launched from the [desktop icon](running-the-app.md) with no keyboard or window chrome
  available.

Entering Play mode (via the **Play** button, from anywhere) always lands on the most recently taken
photo - it re-scans `captures/` fresh each time rather than remembering a stale position from last
visit. An AI edit or a fresh **Click** while reviewing similarly become the new current selection,
the same as if you'd just taken them.

There's no on-screen quit button in Capture mode — switch to Play mode and use **Stop**, or press
keyboard `q` in the terminal, or (on the HDMI backends) Escape / close the window.

### The physical shutter remote and keyboard spacebar

The [Bluetooth shutter remote](shutter-remote.md)'s photo key and the keyboard spacebar behave
differently depending on mode:

* In **Capture mode**, they take a photo immediately, same as **Click**.
* In **Play mode**, they switch back to Capture mode *without* taking a photo — pressing the
  physical shutter while reviewing old photos shouldn't blindly capture whatever the camera happens
  to be pointed at; it just gets you back to the viewfinder to compose deliberately.

The remote's speak key is unaffected by mode — it always bypasses Play mode entirely and acts
immediately on a fresh capture, since requiring on-screen navigation would defeat the point of a
physical, look-free trigger.

## FTP mode (`"mode": "ftp"`)

There's no camera, so there's no Capture mode to switch away from - this is always Play mode. The
app starts on a "Waiting for photos..." placeholder and shows the most recent photo full-screen as
soon as one arrives (see [Receiving Photos over FTP](ftp-setup.md)):

* **Print** / **Speak** / **Publish** / **`<`** / **`>`** / **Page** / **Stop** — same buttons and
  behavior as camera mode's Play mode above, just with no **Capture** button (there's no other mode
  to switch to).

### When a new photo arrives

A newly-received photo always jumps to the front and becomes the current selection - the same way a
fresh AI edit does. If it arrives while you're stepping through older photos, or while a
Publish/Print/AI-edit is quietly working in the background, it interrupts that and shows the new
one right away (any publish/print/edit already in flight keeps working on the photo it started with
- only the screen moves on). If it arrives while a full-screen banner or review/keyboard screen has
temporarily taken over (a "Published!"/print-result banner, the QR-code screen, or the
Send/Reject/Edit review from [Voice-Prompted AI Edits](voice-ai-edits.md)), it's picked up as soon
as that screen closes rather than interrupting it mid-way.

Restarting the app rescans `captures/` for anything already there (e.g. left over from before a
restart) and shows the newest, the same as the first-arrival case.

There's no live viewfinder, no exposure compensation, and no shutter button in this mode - it never
takes a photo itself, only receives ones already taken.

## Camera + FTP mode (`"mode": "camera_ftp"`)

Both of the above at once: the live viewfinder and Capture/Play flow from Camera mode, plus the FTP
receiver from FTP mode running in the background the whole time - see
[Receiving Photos over FTP](ftp-setup.md) for configuring the sending camera's side. The app starts
in Capture mode, same as plain Camera mode.

A photo arriving over FTP behaves exactly as described in
[When a new photo arrives](#when-a-new-photo-arrives) above - it jumps to the front and interrupts
whatever's on screen (Capture mode's live viewfinder included), the same way it would in plain FTP
mode. The live viewfinder itself keeps running in the background while that photo is shown; press
**Capture** to go back to it.

This is useful when you want the device's own camera and an external camera's FTP-transfer feature
(e.g. a Sony body) both feeding the same `captures/` folder and review flow, rather than choosing
one or the other.
