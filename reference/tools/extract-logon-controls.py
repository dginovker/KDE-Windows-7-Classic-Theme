#!/usr/bin/env python3
"""Extract the composed footer controls from our genuine 96-DPI Windows captures."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / 'plasma/logon/art'
GREETER = ROOT / 'plasma/sddm/art'
REF = ROOT / 'reference/screenshots'


def lift(target, background, box, plate=None):
    # Solve Windows' alpha blend against the known wallpaper. The source
    # plate gives the minimum alpha for Ease of Access; its glyph raises it.
    result = target.crop(box).convert('RGBA')
    for y in range(result.height):
        for x in range(result.width):
            pixel = result.getpixel((x, y))[:3]
            behind = background.getpixel((box[0] + x, box[1] + y))
            alpha = plate.getpixel((x, y)) if plate else 255
            if not plate and x in (0, result.width - 1) and y in (0, result.height - 1):
                alpha = 0
            for c, b in zip(pixel, behind):
                delta = c - b
                if delta:
                    limit = 255 - b if delta > 0 else b
                    alpha = max(alpha, (255 * abs(delta) + limit - 1) // limit)
            color = tuple(round(b + (c - b) * 255 / alpha) for c, b in zip(pixel, behind)) if alpha else (0, 0, 0)
            result.putpixel((x, y), (*color, alpha))
    return result


def main(shared=SHARED, greeter=GREETER):
    lock = Image.open(REF / 'w7-lock.png').convert('RGB')
    login = Image.open(REF / 'w7-login.png').convert('RGB')
    background = Image.open(SHARED / 'background.jpg').convert('RGB').resize(lock.size, Image.Resampling.BICUBIC)
    plate = Image.open(SHARED / 'button.png').getchannel('A')
    # The plate is nine-sliced to the displayed 38px; only the centre stretches.
    mask = Image.new('L', (38, 28))
    mask.paste(plate.crop((0, 0, 9, 28)), (0, 0))
    mask.paste(plate.crop((9, 0, 26, 28)).resize((20, 28)), (9, 0))
    mask.paste(plate.crop((26, 0, 35, 28)), (29, 0))
    lift(lock, background, (34, 738, 72, 766), mask).save(shared / 'accessibility.png')
    power = lift(login, lock, (1188, 738, 1246, 766))
    power.crop((0, 0, 38, 28)).save(greeter / 'power-main.png')
    power.crop((38, 0, 58, 28)).save(greeter / 'power-menu.png')


if __name__ == "__main__":
    main()
