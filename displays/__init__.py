from .base import BaseDisplay
from .widgets import Button


def create_display(settings=None):
    """Instantiate the display backend selected by settings["display"]["type"]."""

    settings = settings or {}
    display_settings = settings.get("display", {})
    display_type = display_settings.get("type", "ili9486")

    if display_type == "hdmi":
        from .hdmi_display import HDMIDisplay
        return HDMIDisplay(**display_settings.get("hdmi", {}))

    if display_type == "ili9486":
        from .ili9486_display import ILI9486Display
        return ILI9486Display(**display_settings.get("ili9486", {}))

    raise ValueError(f"Unknown display type: {display_type!r}")


__all__ = ["BaseDisplay", "Button", "create_display"]
