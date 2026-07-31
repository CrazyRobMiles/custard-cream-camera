import time

from PIL import Image, ImageDraw, ImageFont


def _offset(size, span, align, low_value, margin):
    """Position of one axis: `align` picks which edge `margin` is measured from."""
    if align == low_value:
        return margin
    return size - span - margin


def apply_watermark(img, watermark_path, settings):
    """Composites the configured watermark onto a copy of img (RGB), scaled to a fraction of
    img's width (aspect-preserved) and aligned to a corner. Returns a new image - img itself is
    left untouched.
    """
    mark = Image.open(watermark_path).convert("RGBA")

    width_fraction = settings.get("width_fraction", 0.2)
    target_w = max(1, round(img.width * width_fraction))
    target_h = max(1, round(mark.height * (target_w / mark.width)))
    mark = mark.resize((target_w, target_h), Image.LANCZOS)

    margin_x = round(img.width * settings.get("margin_fraction", 0.02))
    margin_y = round(img.height * settings.get("margin_fraction", 0.02))

    x = _offset(img.width, target_w, settings.get("horizontal_align", "right"), "left", margin_x)
    y = _offset(img.height, target_h, settings.get("vertical_align", "bottom"), "top", margin_y)

    result = img.convert("RGB")
    result.paste(mark, (x, y), mark)  # mark's own alpha channel as the paste mask
    return result


def apply_datestamp(img, settings, timestamp):
    """Draws a date/time stamp (from `timestamp`, a Unix time) onto a copy of img (RGB), with a
    semi-transparent background box behind the text for legibility over busy photos. Returns a
    new image - img itself is left untouched.
    """
    text = time.strftime(settings.get("format", "%Y-%m-%d %H:%M"), time.localtime(timestamp))

    font_size = max(10, round(img.height * settings.get("font_fraction", 0.035)))
    font = ImageFont.truetype(
        settings.get("font", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"), font_size
    )

    margin_x = round(img.width * settings.get("margin_fraction", 0.02))
    margin_y = round(img.height * settings.get("margin_fraction", 0.02))

    h_align = settings.get("horizontal_align", "left")
    v_align = settings.get("vertical_align", "bottom")
    anchor = ("l" if h_align == "left" else "r") + ("a" if v_align == "top" else "d")

    x = margin_x if h_align == "left" else img.width - margin_x
    y = margin_y if v_align == "top" else img.height - margin_y

    # Drawn on a transparent overlay and alpha-composited, rather than straight onto an RGB
    # image, so the background box can be semi-transparent instead of a flat opaque block.
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    pad = round(font_size * 0.3)
    bbox = draw.textbbox((x, y), text, font=font, anchor=anchor)
    draw.rectangle(
        (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
        fill=tuple(settings.get("background_colour", [0, 0, 0, 140])),
    )
    draw.text((x, y), text, font=font, fill=tuple(settings.get("text_colour", [255, 255, 255, 255])), anchor=anchor)

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
