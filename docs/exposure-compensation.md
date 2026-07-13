# Exposure Compensation

The camera always runs with auto-exposure enabled - there's no manual shutter speed/gain control - but small "EV-"/"EV+" buttons in the top corners of the live viewfinder let you bias the auto-exposure algorithm by a number of EV stops, which is enough to rescue a backlit subject (positive EV) or an overexposed bright scene (negative EV) without giving up auto-exposure entirely. The current offset is shown at the top of the viewfinder whenever it's non-zero, and resets to the default each time the app starts (it isn't saved back to `settings.json`).

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
