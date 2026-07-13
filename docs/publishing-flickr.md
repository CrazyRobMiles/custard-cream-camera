# Publishing to Flickr

The **Publish** button (in [Play mode](capture-and-play-modes.md)) uploads the currently displayed photo to Flickr, tagged with whatever's configured in `settings.json`. This is built as a pluggable layer in [publishers/](../publishers/) — the same shape as [displays/](../displays/) — so other services (Instagram, a self-hosted gallery, whatever) could be added later as siblings to `flickr_publisher.py` without touching `magic_camera.py` beyond a new `"type"` branch in `publishers/__init__.py`.

## One-time setup

Flickr uses OAuth 1.0a, which needs a real browser to authorize the app — but only **once**. This is deliberately kept separate from the main camera app:

1. Get an API key and secret from [flickr.com/services/apps/create](https://www.flickr.com/services/apps/create/) (needs your Pro account login).
2. Set them as environment variables (same reasoning as the Gemini API key — never stored in `settings.json`, which is checked into git):
   ```bash
   export FLICKR_API_KEY="your-api-key"
   export FLICKR_API_SECRET="your-api-secret"
   ```
3. Run the one-time setup script:
   ```bash
   python setup_flickr_auth.py
   ```
   It prints a URL — open it in a browser on *any* device (your phone is fine, it doesn't have to be the Pi), log into Flickr, authorize the app, and paste the verification code it gives you back into the terminal. This caches an access token locally (via `flickrapi`'s own cache, typically `~/.flickr/`).

After that, **Publish** works with no further browser interaction — `magic_camera.py` only ever does the upload itself, using the cached token. If it's ever missing or expired, publishing fails with a clear message pointing back at this script rather than trying to prompt interactively (there's no browser available from a background upload thread).

If launching from a desktop icon, add the two `export` lines to `~/.bashrc` so they're set before `run_magic_camera.sh` runs — same as the Gemini API key.

## Configuration

```json
"publish": {
    "type": "flickr",
    "flickr": {
        "api_key_env": "FLICKR_API_KEY",
        "api_secret_env": "FLICKR_API_SECRET",
        "tags": "custardcreamcamera",
        "is_public": true,
        "token_cache_dir": null
    }
}
```

* `"tags"` — space-separated tags applied to every upload; multi-word tags need their own quotes inside the string, e.g. `"tags": "custardcreamcamera \"family holiday\""`.
* `"is_public"` — `true` posts immediately visible to anyone on Flickr; set `false` for private (only you) instead.
* `"token_cache_dir"` — leave `null` to use `flickrapi`'s own default cache location; only set this if you need the token stored somewhere specific.

Publishing runs on a background thread, the same way the AI edit does, so the viewfinder and other buttons stay responsive during the upload.
