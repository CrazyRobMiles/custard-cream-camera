from .base import BasePublisher


def create_publisher(settings=None):
    """Instantiate the publish backend selected by settings["publish"]["type"]."""

    settings = settings or {}
    publish_settings = settings.get("publish", {})
    publisher_type = publish_settings.get("type", "flickr")

    if publisher_type == "flickr":
        from .flickr_publisher import FlickrPublisher
        return FlickrPublisher(**publish_settings.get("flickr", {}))

    if publisher_type == "bsky":
        from .bsky_publisher import BskyPublisher
        return BskyPublisher(**publish_settings.get("bsky", {}))

    raise ValueError(f"Unknown publisher type: {publisher_type!r}")


__all__ = ["BasePublisher", "create_publisher"]
