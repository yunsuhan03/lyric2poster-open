"""Step 4: add the title and artist as real text, so the image model never has to draw letters."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

_BOLD = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]
_REGULAR = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
]


def _font(size: int, bold: bool) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in _BOLD if bold else _REGULAR:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words or [text]:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def add_title_overlay(png: bytes, title: str, artist: str) -> bytes:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    w, h = image.size
    margin = int(w * 0.08)
    max_width = w - 2 * margin

    scrim_h = int(h * 0.36)
    ramp = Image.new("L", (1, scrim_h))
    ramp.putdata([int(210 * (y / (scrim_h - 1)) ** 1.5) for y in range(scrim_h)])
    scrim = Image.new("RGBA", (w, scrim_h), (0, 0, 0, 255))
    scrim.putalpha(ramp.resize((w, scrim_h)))
    image.alpha_composite(scrim, (0, h - scrim_h))

    draw = ImageDraw.Draw(image)
    size = int(h * 0.062)
    while True:
        title_font = _font(size, bold=True)
        lines = _wrap(draw, title, title_font, max_width)
        if (len(lines) <= 2 and max(draw.textlength(x, font=title_font) for x in lines) <= max_width) or size <= 18:
            break
        size -= 2
    artist_font = _font(max(int(size * 0.5), 14), bold=False)

    line_h = int(size * 1.18)
    artist_h = int(artist_font.size * 1.4) if hasattr(artist_font, "size") else 24
    y = h - margin - artist_h - line_h * len(lines)
    for line in lines[:2]:
        draw.text((margin, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += line_h
    draw.text((margin, y + int(size * 0.1)), artist, font=artist_font, fill=(235, 235, 235, 255))

    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG")
    return out.getvalue()
