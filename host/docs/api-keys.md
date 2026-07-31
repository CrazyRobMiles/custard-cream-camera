# Storing API Keys on the Device

API keys are needed depending on which features you use:

* `GOOGLE_API_KEY` — [Voice-Prompted AI Edits](voice-ai-edits.md), from [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
* `FLICKR_API_KEY` / `FLICKR_API_SECRET` — [Publishing to Flickr](publishing-flickr.md), from [flickr.com/services/apps/create](https://www.flickr.com/services/apps/create/).
* `BSKY_HANDLE` / `BSKY_APP_PASSWORD` — [Publishing to Bluesky](publishing-bsky.md), an app password from [bsky.app/settings/app-passwords](https://bsky.app/settings/app-passwords) (not your main account password).
* `CUSTARD_CREAM_SERVER_EMAIL` / `CUSTARD_CREAM_SERVER_PASSWORD` — publishing to a self-hosted custard-cream-server instance, the login for this device's account on that server.

All of these are read from environment variables, never from `settings.json` — that file is checked into git, so committing real keys into it would leak them into the repo's history. The question this page actually answers is: how do you make sure those environment variables are set automatically every time the app starts on the device, without typing `export` by hand each session?

These are separate from whatever keys the [camera app](../../camera/) uses — even if both publish to the same accounts, each app reads its own `secrets.sh` and has its own environment, since they're meant to run on separate devices.

## Option A: `secrets.sh`, sourced by the launcher (recommended)

[run_custard_cream_camera_host.sh](../run_custard_cream_camera_host.sh) automatically sources `secrets.sh` next to it, if that file exists, before starting the app - this works regardless of how the app is launched (terminal, desktop icon, application menu), since it's the launcher script itself doing the sourcing rather than relying on some shell startup mechanism to have run first.

`secrets.sh` is listed in `.gitignore`, so it's never committed - only [secrets.sh.example](../secrets.sh.example) (a template with placeholder values) is tracked in git.

To set it up:

```bash
cp secrets.sh.example secrets.sh
chmod 600 secrets.sh   # readable/writable by you only
```

Then edit `secrets.sh` and fill in real values:

```bash
export GOOGLE_API_KEY="your-gemini-api-key"
export FLICKR_API_KEY="your-flickr-api-key"
export FLICKR_API_SECRET="your-flickr-api-secret"
export BSKY_HANDLE="your-handle.bsky.social"
export BSKY_APP_PASSWORD="your-bsky-app-password"
```

That's it - `run_custard_cream_camera_host.sh` picks it up automatically next time it runs, whether that's from a terminal or the desktop icon.

## Option B: shell configuration (`~/.bashrc`)

Add the `export` lines to `~/.bashrc` (or `~/.profile`, depending on your shell setup). This works reliably when you launch the app **from a terminal**, but is less reliable from the **desktop icon** - see [Which to use](#which-to-use) below, and the equivalent section in the [camera app's api-keys.md](../../camera/docs/api-keys.md#option-b-shell-configuration-bashrc) for the full reasoning (identical here).

## Which to use

* Only ever launching from a terminal? Either works equally well.
* Launching from the desktop icon (the common case for a device with no keyboard)? Use **Option A** - it's the one guaranteed to work regardless of desktop environment quirks.
