import os

import flickrapi

from .base import BasePublisher


class FlickrPublisher(BasePublisher):
    """Publishes photos to Flickr via the flickrapi package.

    Flickr auth is OAuth 1.0a, which needs a browser once to authorize the app - that has to
    happen ahead of time via `setup_flickr_auth.py`, run manually from a terminal, not from here.
    This class only ever does the upload itself, assuming a valid cached token already exists;
    if it doesn't, publish() raises with a clear pointer back to that setup script rather than
    trying to prompt interactively (there's no terminal/browser available when this runs from
    the camera's background publish thread).
    """

    name = "flickr"

    def __init__(self, api_key_env="FLICKR_API_KEY", api_secret_env="FLICKR_API_SECRET",
                 tags="", is_public=True, token_cache_dir=None):
        api_key = os.environ.get(api_key_env)
        api_secret = os.environ.get(api_secret_env)
        if not api_key or not api_secret:
            raise RuntimeError(
                f"Flickr API credentials missing - set {api_key_env} and {api_secret_env} "
                "environment variables. Get them from https://www.flickr.com/services/apps/create/"
            )

        cache_kwargs = {"token_cache_location": token_cache_dir} if token_cache_dir else {}
        self.flickr = flickrapi.FlickrAPI(api_key, api_secret, format="parsed-json", **cache_kwargs)
        self.tags = tags
        self.is_public = is_public

    def publish(self, image_path, tags=None):
        if not self.flickr.token_valid(perms="write"):
            raise RuntimeError(
                "Not authorized with Flickr yet - run `python setup_flickr_auth.py` once from a "
                "terminal (with FLICKR_API_KEY/FLICKR_API_SECRET set) to authorize this app."
            )

        combined_tags = " ".join(t for t in (self.tags, tags) if t)
        response = self.flickr.upload(
            filename=str(image_path),
            tags=combined_tags,
            is_public=1 if self.is_public else 0,
        )
        return response.attrib.get("stat") == "ok"
