#!/usr/bin/env python3
"""Validate captures from the documented Mouse Actions round trip in the lab.

Run after capturing at 1280×800, 100% scale, right-clicking at (100, 250).
Record the Windows appletsrc before selection, after selection, and after manually
restoring the original action and its settings. Compare only actual lab output.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

from PIL import Image


def text(path, box):
    image = Image.open(path).crop(box)
    with tempfile.NamedTemporaryFile(suffix='.png') as crop:
        image.resize((3 * image.width, 3 * image.height)).save(crop.name)
        return subprocess.check_output(['tesseract', crop.name, 'stdout', '--psm', '6'],
                                       stderr=subprocess.DEVNULL, text=True).casefold()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    out = parser.parse_args().evidence
    images = out / 'optin-final'
    for stem in ('current-after-install', 'windows-before-optin', 'current-after-optin',
                 'windows-restored', 'current-after-uninstall', 'windows-opted-in', 'windows-persisted'):
        ocr = text(images / f'{stem}.png', (105, 253, 342, 494))
        labels = ('view', 'sort by', 'refresh', 'personalize') if stem in ('windows-opted-in', 'windows-persisted') else (
            'create new', 'icons', 'desktop and wallpaper')
        assert all(label in ocr for label in labels), (stem, ocr)
    before = (out / 'optin-windows-before.kconfig').read_bytes()
    after = (out / 'optin-windows-after.kconfig').read_bytes()
    reverted = (out / 'optin-windows-restored.kconfig').read_bytes()
    assert b'MiddleButton;NoModifier=org.kde.paste\n' in before
    assert b'plugin=org.kde.plasma.pager\n' in before
    assert after == before.replace(b'RightButton;NoModifier=org.kde.contextmenu\n',
                                  b'RightButton;NoModifier=org.win7classic.desktopmenu\n', 1)
    assert reverted == before, 'manual undo changed more than the selected binding or its restored options'
    for first, last in (('optin-before-removal.state', 'optin-after-removal.state'),
                        ('optin-kate-before.txt', 'optin-kate-after.txt')):
        assert (out / first).read_bytes() == (out / last).read_bytes(), (first, last)
    print('Observed menus, scoped binding change, restored options, live/profile hashes and process identities passed.')


if __name__ == '__main__':
    main()
