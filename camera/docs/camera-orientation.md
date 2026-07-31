# Camera Orientation

If the live viewfinder (or captured photos) comes out flipped or upside down - typically because the HQ camera sensor ended up mounted rotated in the enclosure - correct it with `"hflip"`/`"vflip"` under `"camera"` in [settings.json](../settings.json), rather than physically remounting the sensor or rotating images in software after the fact:

```json
"camera": {
    "hflip": true,
    "vflip": true
}
```

Both `true` (the default in this repo's `settings.json`) corrects a sensor mounted rotated 180 degrees; use just one of the two if your image is mirrored on a single axis instead. This is applied once, in the camera's own capture pipeline via `libcamera`'s `Transform`, so it covers the viewfinder, saved photos, and whatever gets sent off for AI editing - not something each part of the app has to individually work around.
