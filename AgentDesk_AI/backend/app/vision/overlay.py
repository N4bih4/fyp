"""Draw the candidate boxes, with their numbers, on the picture that is sent to the vision model."""
from __future__ import annotations

import io

from .boxes import Box

MAX_WIDTH = 960
_COLORS = [(230, 25, 75), (0, 130, 200), (60, 180, 75), (245, 130, 48), (145, 30, 180), (0, 150, 150), (200, 0, 140), (170, 110, 40)]


def draw(image, boxes: list[Box]):
    """A copy of `image` with every box outlined and numbered. Returns (picture, scale): scale = picture width / image width."""
    from PIL import Image, ImageDraw, ImageFont
    scale = min(1.0, MAX_WIDTH / image.width)
    pic = image.convert("RGB")
    if scale < 1.0:
        pic = pic.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(pic)
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    for box in boxes:
        color = _COLORS[box.id % len(_COLORS)]
        l, t, r, b = (round(v * scale) for v in box.rect)
        d.rectangle([l, t, r, b], outline=color, width=2)
        tag = str(box.id)
        w = d.textlength(tag, font=font) + 6
        top = max(0, t - 15)
        d.rectangle([l, top, l + w, top + 15], fill=color)
        d.text((l + 3, top + 1), tag, fill="white", font=font)
    return pic, scale


def to_jpeg(picture, quality: int = 80) -> bytes:
    buf = io.BytesIO()
    picture.save(buf, "JPEG", quality=quality)
    return buf.getvalue()
