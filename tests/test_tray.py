#!/usr/bin/env python3
"""Focused disposable-lab check with final candidate installed, stock layout and current/100%."""
import json
from pathlib import Path
import sys
import time

from PIL import Image
from lab import VM, digest, shot, toggle, user, vmctl, wait_for
from test_calendar import is_open
from test_taskbar import FACE, tray_left

QICON = '''from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
app = QApplication([])
assert QIcon.themeName() == 'Win7-Classic', QIcon.themeName()
names = ['audio-volume-medium-symbolic', 'audio-volume-muted-symbolic',
         'network-wired-disconnected-symbolic', 'arrow-up-symbolic']
def icons():
    result = []
    for name in names:
        icon = QIcon.fromTheme(name)
        assert not icon.isNull(), name
        result.append(icon.pixmap(24, 24).toImage())
    return result
classic = icons()
QIcon.setThemeName('breeze')
for name, themed, stock in zip(names, classic, icons()):
    assert themed == stock, name
    print(name + ': exact Breeze pixels at 24px in a Qt Widgets process')
'''


def main(out):
    out.mkdir(parents=True, exist_ok=True)

    def snap(name):
        path = out / f'{name}.png'
        shot(path)
        with Image.open(path) as image:
            return image.convert('RGB')

    vmctl.start(VM)
    assert user('~/.local/bin/win7-classic status') == 'current'
    output, = json.loads(user('kscreen-doctor -j'))['outputs']
    scale = f"kscreen-doctor output.{output['name']}.scale."
    assert output['scale'] == 1
    before = digest()
    sink = '@DEFAULT_AUDIO_SINK@'
    original = user(f'wpctl get-volume {sink}')
    try:
        user(f'wpctl set-volume {sink} 0.40; wpctl set-mute {sink} 0')
        toggle('windows')
        vmctl.pointer(VM, 640, 400)
        time.sleep(2)
        image = snap('1x-tray')
        left = tray_left(image)
        marker = left + 21
        volume = left + 99
        for offset in (21, 47, 73, 99):
            x = left + offset
            assert any(image.getpixel((u, y)) != FACE for u in range(x - 6, x + 7) for y in range(770, 786)), offset
        for offset in (34, 60, 86):
            x = left + offset
            assert all(image.getpixel((x, y)) == FACE for y in range(770, 786)), offset
        desktop = (900, 350, 1260, 700)
        vmctl.pointer(VM, marker, 778, 'left')
        wait_for(lambda: snap('1x-expanded').crop(desktop) != image.crop(desktop), 'left marker opens hidden items')
        vmctl.pointer(VM, marker, 778, 'left')
        vmctl.pointer(VM, 640, 400)
        wait_for(lambda: snap('1x-collapsed').crop(desktop) == image.crop(desktop), 'same marker closes hidden items')
        vmctl.pointer(VM, volume, 778, 'middle')
        wait_for(lambda: '[MUTED]' in user(f'wpctl get-volume {sink}'), 'stock middle-click mutes')
        vmctl.pointer(VM, volume, 778, 'middle')
        wait_for(lambda: '[MUTED]' not in user(f'wpctl get-volume {sink}'), 'stock middle-click unmutes')
        vmctl.pointer(VM, volume, 778, 'left')
        wait_for(lambda: snap('1x-volume-controls').crop(desktop) != image.crop(desktop), 'stock volume controls')
        vmctl.pointer(VM, 640, 400, 'left')
        wait_for(lambda: snap('1x-volume-closed').crop(desktop) == image.crop(desktop), 'volume click-away')
        print(user("systemd-run --user --wait --pipe --collect -q /usr/bin/python - <<'PYQT'\n" + QICON + 'PYQT'))
        print('100%: stock tray leading marker, compact 26px pitch, real volume interaction')

        user(scale + '1.5')
        time.sleep(3)
        scaled = snap('1.5x-tray')
        assert scaled.size == (1280, 800)
        vmctl.pointer(VM, 1280 - 75, 800 - 43, 'left')
        wait_for(lambda: is_open(snap('1.5x-calendar'), 1.5), 'calendar anchor at 150%')
        vmctl.keys(VM, 'KEY_ESC')
        wait_for(lambda: not is_open(snap('1.5x-calendar-dismissed'), 1.5), 'scaled Escape dismisses calendar')
    finally:
        user(f"wpctl set-volume {sink} {original.split()[1]}; wpctl set-mute {sink} {int('[MUTED]' in original)}")
        user(scale + '1')
        if user('~/.local/bin/win7-classic status') == 'windows':
            toggle('current')
    assert digest() == before, 'current profile not restored byte-for-byte'
    print('150% calendar anchor at 1280×800 physical, current profile restored')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
