#!/usr/bin/env python3

"""Generate the macOS .icns asset used by the native app bundle."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size):
    candidates = (
        "/System/Library/Fonts/SFNSRounded.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: generate_icon.py OUTPUT.icns")

    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (64, 64, 960, 960),
        radius=220,
        fill=(20, 22, 28, 255),
        outline=(255, 255, 255, 255),
        width=34,
    )
    label_font = font(400)
    bounds = draw.textbbox((0, 0), "AI", font=label_font)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    position = ((size - text_width) / 2, (size - text_height) / 2 - bounds[1] - 12)
    draw.text(position, "AI", fill=(255, 255, 255, 255), font=label_font)

    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="ICNS")


if __name__ == "__main__":
    main()
