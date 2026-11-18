#!/usr/bin/env python3
"""Reuse the genuine calendar dial, retouching only the frozen 7:47:00 hands."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
face = Image.open(ROOT / 'reference/screenshots/w7-calendar.png').convert('RGB').crop((1134, 554, 1265, 683))
mask = Image.new('1', face.size)
pen = ImageDraw.Draw(mask)
pen.line([(18, 54), (65, 64)], fill=1, width=7)
pen.line([(37, 87), (65, 64)], fill=1, width=7)
pen.rectangle((63, 20, 65, 84), fill=1)  # leave the twelve o'clock tick
pen.ellipse((60, 59, 69, 70), fill=1)
# Interpolate from clean samples across each thin hand. Use the shorter span
# to avoid smearing the curved highlight along the length of a hand.
for y in range(face.height):
    for x in range(face.width):
        if not mask.getpixel((x, y)):
            continue
        spans = []
        for dx, dy in [(1, 0), (0, 1), (1, 1), (1, -1)]:
            a = b = 1
            while mask.getpixel((x - a * dx, y - a * dy)):
                a += 1
            while mask.getpixel((x + b * dx, y + b * dy)):
                b += 1
            spans.append((a + b, a, b, dx, dy))
        dist, a, b, dx, dy = min(spans)
        left = face.getpixel((x - a * dx, y - a * dy))
        right = face.getpixel((x + b * dx, y + b * dy))
        face.putpixel((x, y), tuple(round((l * b + r * a) / dist) for l, r in zip(left, right)))
face.save(ROOT / 'plasma/org.win7classic.clock/contents/ui/calendar-dial.png')
