# Reviewing Received Photos

There's only one mode - there's no camera, so there's no viewfinder/capture mode to switch away from. The app starts on a "Waiting for photos..." placeholder and shows the most recent photo full-screen as soon as one arrives (see [Receiving Photos over FTP](ftp-setup.md)):

* **Print** / **Speak** / **Publish** — act immediately on whichever photo is currently shown. **Speak** is hold-to-talk: press to record an editing instruction, release to send - see [Voice-Prompted AI Edits](voice-ai-edits.md). **Publish** opens a menu of every *enabled* destination (Flickr, Bluesky, Custard Cream Server, ...) — tap one to send this photo there, with a "Published to \<name\>!" confirmation naming which one; publishing to more than one destination means pressing **Publish** again afterwards and picking another. If only one destination is enabled, Publish skips the menu and sends straight to it. See [Printing](printing.md) and [Publishing to Flickr](publishing-flickr.md) for what each of those actually does.
* **`<`** / **`>`** (small buttons on the left/right screen edges) — step to the previous/next photo one at a time, newest-first.
* **Page** (top-right corner) — opens a 3×3 grid of the current page of 9 photos; tapping a thumbnail makes it the current selection and returns to the single-photo view. **Left**/**Right** in the grid page through older/newer groups of 9; **Back** returns to the single-photo view without changing the selection.
* **Stop** (top-left corner) — exits the app cleanly. This is the only on-screen way to quit, for when it's launched from the [desktop icon](running-the-app.md) with no keyboard or window chrome available.

## When a new photo arrives

A newly-received photo always jumps to the front and becomes the current selection - the same way a fresh AI edit does in the camera app. If it arrives while you're stepping through older photos, or while a Publish/Print/AI-edit is quietly working in the background, it interrupts that and shows the new one right away (any publish/print/edit already in flight keeps working on the photo it started with - only the screen moves on). If it arrives while a full-screen banner or review/keyboard screen has temporarily taken over (a "Published!"/print-result banner, the QR-code screen, or the Send/Reject/Edit review from [Voice-Prompted AI Edits](voice-ai-edits.md)), it's picked up as soon as that screen closes rather than interrupting it mid-way.

Restarting the app rescans `captures/` for anything already there (e.g. left over from before a restart) and shows the newest, the same as the first-arrival case.

## What's not here

There's no live viewfinder, no exposure compensation, and no shutter button - this app never takes a photo itself, only receives ones already taken. See [Capture Mode and Play Mode](../../camera/docs/capture-and-play-modes.md) in the camera app's docs if you're looking for that.
