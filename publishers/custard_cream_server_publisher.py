import os
from pathlib import Path

import requests

from .base import BasePublisher


class CustardCreamServerPublisher(BasePublisher):
    """Publishes photos to a self-hosted custard-cream-server instance.

    Auth is a login (email+password) against the server's shared user database,
    exchanged for a short-lived JWT sent back as `Authorization: Bearer`. Unlike
    Flickr's cached OAuth token, the JWT is cheap to fetch fresh on every publish
    call (matching the Bluesky publisher's pattern) - uploads are infrequent, so
    there's no need for a persisted token cache in v1.

    publish() only returns True/False per the base interface, so on success this
    stashes the server's response (picture URL + three-word phrase) on
    `last_result` for the caller to read afterward and use to show a QR code and
    the phrase on screen.
    """

    name = "custard_cream_server"
    button_text = "CC Server"

    def __init__(self, base_url, email_env="CUSTARD_CREAM_SERVER_EMAIL",
                 password_env="CUSTARD_CREAM_SERVER_PASSWORD", timeout_seconds=15,
                 qr_hold_seconds=8):
        if not base_url:
            raise RuntimeError("Custard Cream Server publisher needs a 'base_url' setting")

        self.base_url = base_url.rstrip("/")
        self.email = os.environ.get(email_env)
        self.password = os.environ.get(password_env)
        if not self.email or not self.password:
            raise RuntimeError(
                f"Custard Cream Server credentials missing - set {email_env} and "
                f"{password_env} environment variables (see secrets.sh.example)."
            )

        self.timeout_seconds = timeout_seconds
        self.qr_hold_seconds = qr_hold_seconds
        self.last_result = None

    def _login(self):
        response = requests.post(
            f"{self.base_url}/login",
            json={"email": self.email, "password": self.password},
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Custard Cream Server login failed ({response.status_code}) - "
                "check the camera account credentials configured on the server."
            )
        return response.json()["token"]

    def publish(self, image_path, tags=None):
        self.last_result = None
        token = self._login()

        image_path = Path(image_path)
        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

        with open(image_path, "rb") as f:
            response = requests.post(
                f"{self.base_url}/pictures",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                files={"image": (image_path.name, f, mime_type)},
                timeout=self.timeout_seconds,
            )

        if response.status_code != 201:
            raise RuntimeError(
                f"Custard Cream Server upload failed ({response.status_code}): {response.text}"
            )

        self.last_result = response.json()
        return True
