# Publishing to Bluesky

The **Publish** button (in [Play mode](capture-and-play-modes.md)) opens a menu of every configured destination — tapping **Bluesky** there posts the currently displayed photo, using the [atproto](https://atproto.blue) package. This is a sibling of [flickr_publisher.py](../publishers/flickr_publisher.py) in the same pluggable [publishers/](../publishers/) layer — see [Publishing to Flickr](publishing-flickr.md) for the general shape.

## One-time setup

Unlike Flickr, Bluesky doesn't need a browser-based OAuth flow at all — just a handle and an **app password**:

1. Go to [bsky.app/settings/app-passwords](https://bsky.app/settings/app-passwords) while logged into your Bluesky account and create a new app password. Use this, never your real account password — the camera stores it in an environment variable, and an app password can be revoked independently if it's ever compromised.
2. Set your handle and the app password as environment variables (same reasoning as the other API keys — never stored in `settings.json`, which is checked into git):
   ```bash
   export BSKY_HANDLE="your-handle.bsky.social"
   export BSKY_APP_PASSWORD="your-bsky-app-password"
   ```

For these to be set automatically every time the app runs (including from the desktop icon), see [Storing API Keys on the Device](api-keys.md) — same as the other keys.

## Configuration

```json
"publish": {
    "bsky": {
        "enabled": true,
        "handle_env": "BSKY_HANDLE",
        "app_password_env": "BSKY_APP_PASSWORD",
        "text": "",
        "alt_text": ""
    }
}
```

* `"enabled"` — set to `false` to take Bluesky out of the Publish menu without deleting the rest of its config; defaults to `true` if omitted.
* `"text"` — fixed text posted with every photo (e.g. a hashtag). Left empty by default.
* `"alt_text"` — accessibility alt text attached to the image itself.

Publishing runs on a background thread, the same way the AI edit does, so the viewfinder and other buttons stay responsive during the upload. Note that Bluesky rejects images over roughly 1MB — the camera doesn't currently downscale before upload, so very large photos may fail to publish with an error from the server.
