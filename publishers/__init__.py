from .base import BasePublisher

# Display label for each known publisher type, in the order they should appear in the
# destination menu. A type only shows up there if it also has a config block under
# settings["publish"] - so leaving one out of settings.json is how you disable it.
PUBLISHER_LABELS = {
    "flickr": "Flickr",
    "bsky": "Bluesky",
    "custard_cream_server": "Custard Cream Server",
}


def _publisher_class(publisher_type):
    if publisher_type == "flickr":
        from .flickr_publisher import FlickrPublisher
        return FlickrPublisher

    if publisher_type == "bsky":
        from .bsky_publisher import BskyPublisher
        return BskyPublisher

    if publisher_type == "custard_cream_server":
        from .custard_cream_server_publisher import CustardCreamServerPublisher
        return CustardCreamServerPublisher

    raise ValueError(f"Unknown publisher type: {publisher_type!r}")


def available_publishers(settings=None):
    """Returns [(type, button_text), ...] for every publisher configured under settings["publish"]
    that isn't explicitly disabled with "enabled": false (missing "enabled" defaults to on).
    button_text is each publisher class's own short label - see Publish menu button widths."""

    publish_settings = (settings or {}).get("publish", {})
    return [
        (publisher_type, _publisher_class(publisher_type).button_text)
        for publisher_type in PUBLISHER_LABELS
        if publisher_type in publish_settings and publish_settings[publisher_type].get("enabled", True)
    ]


def publisher_label(publisher_type):
    return PUBLISHER_LABELS.get(publisher_type, publisher_type)


def _publisher_kwargs(publish_settings, publisher_type):
    """The config block for publisher_type, minus "enabled" - that key is only read by
    available_publishers(), not by the publisher classes' own constructors."""
    kwargs = dict(publish_settings.get(publisher_type, {}))
    kwargs.pop("enabled", None)
    return kwargs


def create_publisher(settings, publisher_type):
    """Instantiate one publish backend by type, using its config block under settings["publish"]."""

    publish_settings = (settings or {}).get("publish", {})
    publisher_class = _publisher_class(publisher_type)
    return publisher_class(**_publisher_kwargs(publish_settings, publisher_type))


__all__ = ["BasePublisher", "create_publisher", "available_publishers", "publisher_label"]
