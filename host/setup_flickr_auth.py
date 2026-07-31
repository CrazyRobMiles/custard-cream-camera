"""One-time interactive Flickr authorization.

Run this manually from a terminal - not part of the main app - to authorize custard_cream_camera_host.py
to publish to your Flickr account. It opens a 3-legged OAuth 1.0a flow: you visit a URL in any
browser (doesn't have to be on this device), approve the app, and paste back the verification code
Flickr gives you. The resulting access token is cached locally, so this only needs to be done
once per device - after that, the Publish button works without any further browser step. If the
camera app has already been authorized on a different device, this still needs running again
here, since the cached token lives per-machine (typically `~/.flickr/`), not in this repo.

Usage:
    export FLICKR_API_KEY=...
    export FLICKR_API_SECRET=...
    python setup_flickr_auth.py
"""
import os
import sys

import flickrapi

API_KEY_ENV = "FLICKR_API_KEY"
API_SECRET_ENV = "FLICKR_API_SECRET"


def main():
    api_key = os.environ.get(API_KEY_ENV)
    api_secret = os.environ.get(API_SECRET_ENV)
    if not api_key or not api_secret:
        print(
            f"Set {API_KEY_ENV} and {API_SECRET_ENV} first - get them from "
            "https://www.flickr.com/services/apps/create/"
        )
        sys.exit(1)

    flickr = flickrapi.FlickrAPI(api_key, api_secret, format="parsed-json")

    if flickr.token_valid(perms="write"):
        print("Already authorized with write access - nothing to do.")
        return

    flickr.get_request_token(oauth_callback="oob")
    authorize_url = flickr.auth_url(perms="write")
    print(f"Open this URL in a browser and authorize the app:\n\n{authorize_url}\n")
    verifier = input("Paste the verification code Flickr gives you here: ").strip()
    flickr.get_access_token(verifier)
    print("Authorized - the access token is now cached. custard_cream_camera.py can publish to Flickr now.")


if __name__ == "__main__":
    main()
