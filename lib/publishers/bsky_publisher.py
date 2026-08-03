import os

from atproto import Client

from .base import BasePublisher


class BskyPublisher(BasePublisher):
    """Publishes photos to Bluesky via the atproto package.

    Unlike Flickr, Bluesky auth doesn't need a browser-based OAuth flow - it's just a handle plus
    an app password (created at https://bsky.app/settings/app-passwords, not your main account
    password), so login happens directly in publish() with no separate one-time setup script.
    """

    name = "bsky"

    def __init__(self, handle_env="BSKY_HANDLE", app_password_env="BSKY_APP_PASSWORD",
                 text="", alt_text=""):
        self.handle = os.environ.get(handle_env)
        self.app_password = os.environ.get(app_password_env)
        if not self.handle or not self.app_password:
            raise RuntimeError(
                f"Bluesky credentials missing - set {handle_env} and {app_password_env} "
                "environment variables. Create an app password (not your main account password) "
                "at https://bsky.app/settings/app-passwords"
            )

        self.text = text
        self.alt_text = alt_text

    def publish(self, image_path, tags=None, ai_instruction=None):
        client = Client()
        client.login(self.handle, self.app_password)

        post_text = " ".join(t for t in (self.text, tags) if t)
        with open(image_path, "rb") as f:
            image_data = f.read()

        client.send_image(text=post_text, image=image_data, image_alt=self.alt_text)
        return True
