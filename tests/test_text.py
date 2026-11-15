#!/usr/bin/env python3
"""Text rendering in Windows mode (issue #11), compared with the Windows 7 Start menu labels.

Wine's Tahoma is a different font file and FreeType a different rasterizer, so glyphs can't match exactly;
this test pins how close they are (thresholds just above what was measured) so regressions show up.
"""
from pathlib import Path
import sys
import time

from PIL import Image

from lab import ROOT, VM, vmctl, user, toggle, wait_for, install, shot

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-text-test')
REF = ROOT / 'reference/screenshots/w7-menu.png'
FACE = (212, 208, 200)
# Right-column labels: identical text in both menus.
LABELS = [('Documents', 407), ('Pictures', 441), ('Music', 475), ('Games', 512), ('Computer', 546),
          ('Control Panel', 583), ('Devices and Printers', 617), ('Default Programs', 651), ('Help and Support', 685)]


def text_box(image, y):
    points = [(x, yy) for yy in range(y, y + 32) for x in range(262, 402) if image.getpixel((x, yy)) != FACE]
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points) + 1, max(p[1] for p in points) + 1


def measure(path):
    ours, windows = Image.open(path).convert('RGB'), Image.open(REF).convert('RGB')
    diff = pixels = 0
    rows = []
    for name, y in LABELS:
        for yy in range(y + 8, y + 24):
            for x in range(265, 405):
                diff += sum(abs(a - b) for a, b in zip(ours.getpixel((x, yy)), windows.getpixel((x, yy))))
                pixels += 3
        a, b = text_box(ours, y), text_box(windows, y)
        rows.append((name, a[2] - a[0], b[2] - b[0], a[1] - b[1]))
    fringe = lambda image: sum(1 for yy in range(415, 430) for x in range(265, 325) if max(image.getpixel((x, yy))) - min(image.getpixel((x, yy))) > 30)
    return diff / pixels, rows, fringe(ours), fringe(windows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    current_noto = user('fc-match -v "Noto Sans" | grep -E "rgba|hintstyle|lcdfilter"')
    install()
    assert user('fc-match -v "Noto Sans" | grep -E "rgba|hintstyle|lcdfilter"') == current_noto, 'installing changed how other fonts render'
    toggle('windows')
    # plasmashell reads fontconfig at start; reset-failed avoids systemd's restart rate limit.
    user('systemctl --user reset-failed plasma-plasmashell; systemctl --user restart plasma-plasmashell')
    time.sleep(4)
    vmctl.pointer(VM, 25, 777, 'left')
    wait_for(lambda: (shot(OUT / 'menu.png'), Image.open(OUT / 'menu.png').convert('RGB').getpixel((404, 400)))[1] == (64, 64, 64), 'Start menu')
    vmctl.pointer(VM, 640, 790)
    time.sleep(0.5)
    shot(OUT / 'menu.png')
    vmctl.keys(VM, 'KEY_ESC')
    mean, rows, fringe, windows_fringe = measure(OUT / 'menu.png')
    for name, ours, theirs, dy in rows:
        print(f'  {name:22s} width {ours}px (Windows {theirs}px), baseline offset {dy}px')
    print(f'mean difference {mean:.2f}/255 per channel; ClearType-colored pixels in "Documents": {fringe} (Windows {windows_fringe})')
    assert mean <= 12.0, f'label pixels drifted from Windows: {mean:.2f}'
    # Qt lays glyphs out with fractional advances where Windows rounds each one, so labels run up to 3px long.
    assert all(0 <= ours - theirs <= 3 and abs(dy) <= 1 for _, ours, theirs, dy in rows), rows
    assert abs(fringe - windows_fringe) <= windows_fringe * 0.15, 'subpixel (ClearType-like) rendering is off'

    toggle('current')
    assert user('fc-match -v "Noto Sans" | grep -E "rgba|hintstyle|lcdfilter"') == current_noto
    print('current mode fonts render exactly as before')
    crop = Image.new('RGB', (150, 22 * 2), 'white')
    crop.paste(Image.open(REF).convert('RGB').crop((264, 413, 414, 433)), (0, 0))
    crop.paste(Image.open(OUT / 'menu.png').convert('RGB').crop((264, 413, 414, 433)), (0, 22))
    crop.resize((750, 220), Image.NEAREST).save(OUT / 'documents-zoom.png')
    print('ALL TEXT CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
