# Publishing to Flickr

The **Publish** button (see [Reviewing Received Photos](reviewing-photos.md)) opens a menu of every configured destination — tapping **Flickr** there uploads the currently displayed photo, tagged with whatever's configured in `settings.json`. This is built as a pluggable layer in [lib/publishers/](../../lib/publishers/) — the same shape as [lib/displays/](../../lib/displays/) — and shared unchanged with the [camera app](../../camera/). [Bluesky](publishing-bsky.md) is already a sibling of `flickr_publisher.py`, alongside the self-hosted Custard Cream Server backend.

## One-time setup

Flickr uses OAuth 1.0a, which needs a real browser to authorize the app — but only **once per device**. This is deliberately kept separate from the main app:

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
   It prints a URL — open it in a browser on *any* device, log into Flickr, authorize the app, and paste the verification code it gives you back into the terminal. This caches an access token locally (via `flickrapi`'s own cache, typically `~/.flickr/`).

   If the camera app has already been authorized on a *different* device, this still needs running again here — the cached token lives per-machine, not in this repo, so each device that publishes to Flickr needs its own one-time authorization.

   Prefer a device other than this one for opening the browser if you can: doing it directly on this device's own desktop can trigger a keyring/password dialog that stays open (and stays modal) behind the app afterwards, silently blocking all clicks until it's dismissed — see [Touch/clicks stop responding](display-backends.md#touchclicks-stop-responding-but-the-cursor-still-moves).

After that, **Publish** works with no further browser interaction. If the cached token is ever missing or expired, publishing fails with a clear message pointing back at this script.

For these to be set automatically every time the app runs (including from the desktop icon), see [Storing API Keys on the Device](api-keys.md) — same as the Gemini API key.

## Configuration

```json
"publish": {
    "flickr": {
        "enabled": true,
        "api_key_env": "FLICKR_API_KEY",
        "api_secret_env": "FLICKR_API_SECRET",
        "tags": "custardcreamcamera",
        "is_public": true,
        "token_cache_dir": null
    }
}
```

* `"enabled"` — set to `false` to take Flickr out of the Publish menu without deleting the rest of its config; defaults to `true` if omitted.
* `"tags"` — space-separated tags applied to every upload; multi-word tags need their own quotes inside the string, e.g. `"tags": "custardcreamcamera \"family holiday\""`.
* `"is_public"` — `true` posts immediately visible to anyone on Flickr; set `false` for private (only you) instead.
* `"token_cache_dir"` — leave `null` to use `flickrapi`'s own default cache location; only set this if you need the token stored somewhere specific.

Every enabled destination under `"publish"` shows up as its own button in the Publish menu. If only one destination ends up enabled, Publish skips the menu entirely and sends straight to it.

Publishing runs on a background thread, so the app stays responsive during the upload.
