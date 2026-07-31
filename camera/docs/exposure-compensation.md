# Exposure Compensation

Small "EV-"/"EV+" buttons in the top corners of the live viewfinder let you bias the exposure by a number of EV stops - enough to rescue a backlit subject (positive EV) or an overexposed bright scene (negative EV). At EV 0 the camera runs fully auto-exposed as normal. Moving off EV 0 snapshots the auto-exposure algorithm's current shutter speed/gain as a baseline, disables auto-exposure, and explicitly sets a shutter speed scaled by `2^EV` from that baseline - every further +/- press rescales from the same baseline rather than the live (now manually-overridden) reading, so repeated presses give a clean, repeatable offset instead of drifting. Auto-exposure resumes as soon as you return to EV 0.

(An earlier version tried to do this via libcamera's `ExposureValue` control, which is meant to bias AE without disabling it - it turned out to be a no-op on this camera/tuning stack, silently accepted but with no effect on the actual shutter speed, hence the explicit snapshot-and-scale approach instead.)

The current EV offset, plus the actual metered shutter speed and gain, are shown at the top of the viewfinder at all times - useful for confirming the buttons are having a real effect, not just changing the on-screen number. The EV offset resets to the default each time the app starts (it isn't saved back to `settings.json`).

Range and step are configurable under `"exposure"` in [settings.json](../settings.json):

```json
"exposure": {
    "default": 0.0,
    "step": 0.5,
    "min": -2.0,
    "max": 2.0
}
```

This is separate from the manual aperture ring on the lens itself - that's a physical adjustment outside the app's control, and exposure compensation on top of it works the same way it would on any camera with an auto-exposure mode.
