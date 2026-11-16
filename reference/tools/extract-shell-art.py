#!/usr/bin/env python3
"""Extract shell artwork from committed genuine 96-DPI references; never from resampled owner images."""
from pathlib import Path
from PIL import Image
root = Path(__file__).resolve().parents[2]
out = root / 'plasma/org.win7classic.taskbar/contents/ui/assets'
out.mkdir(exist_ok=True)
for name, scene, box in [('search', 'w7-menu', (228, 723, 250, 746)),
                         ('clear', 'w7-search', (231, 723, 253, 746))]:
    Image.open(root / f'reference/screenshots/{scene}.png').convert('RGBA').crop(box).save(out / f'{name}.png')
frame = Image.open(root / 'reference/screenshots/w7-menu.png').convert('RGBA').crop((300, 303, 362, 365))
frame.paste((0, 0, 0, 0), (7, 7, 55, 53))
frame.save(out / 'account-frame.png')
