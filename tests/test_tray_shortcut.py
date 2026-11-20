#!/usr/bin/env python3
"""Use the installed Classic tray's native Keyboard Shortcuts page on a settled lab."""
import argparse
from pathlib import Path
import re
import time

from PIL import Image

from lab import VM, shot, user, vmctl, wait_for
from test_tray import APPLET_CONFIG, REFERENCE, icon_center, label, ocr


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    assert user('/usr/bin/win7-classic status') == 'current'
    accel = '~/.config/kglobalshortcutsrc'
    before = user(f'base64 -w0 {accel}')
    reference = Image.open(REFERENCE).convert('RGB')
    keys = ('KEY_LEFTMETA', 'KEY_LEFTSHIFT', 'KEY_F9')
    chord = 'Meta+Shift+F9'
    crop = (875, 520, 1280, 747)
    assert not user(f'grep -F {chord} {accel}', check=False), f'test chord {chord} already used'

    def snap(name):
        path = out / (name + '.png')
        shot(path)
        return Image.open(path).convert('RGB')

    def click(point, button='left'):
        vmctl.pointer(VM, *point, button)

    def layout():
        return user(f'cat {APPLET_CONFIG}')

    try:
        print(user('/usr/bin/win7-classic windows'))
        group = re.search(r'(?m)^(\[Containments\]\[\d+\]\[Applets\]\[(\d+)\])\n[^\[]*?^plugin=org\.win7classic\.tray$', layout())
        assert group, 'Classic tray missing from the live layout'
        shortcut_group = group[1] + '[Shortcuts]\nglobal='
        assert shortcut_group not in layout(), 'tray did not start without a shortcut'
        tid = group[2]
        action = f'activate widget {tid}'
        call = 'busctl --user call org.kde.kglobalaccel /kglobalaccel org.kde.KGlobalAccel'
        live = f"{call} shortcutKeys as 4 plasmashell '{action}' plasmashell 'Activate Windows 7 Classic notification area Widget'"
        assert user(live) == 'a(ai) 0', 'tray accelerator already registered'
        recorded = user(f'test -f ~/.local/state/win7-classic/current-tray-accelerators.json.ids/{tid} && echo yes', check=False)
        print(f'Tray ID {tid} recorded before assignment: {recorded == "yes"}')
        vmctl.pointer(VM, 820, 690)
        time.sleep(1)
        idle = snap('idle')
        marker = icon_center(idle, reference, (13, 17, 18, 25))
        click(marker)
        vmctl.pointer(VM, 820, 690)
        time.sleep(.6)
        opened = snap('mouse-open').crop(crop).tobytes()
        closed = idle.crop(crop).tobytes()
        assert opened != closed, 'pointer baseline did not open the hidden-items popup'
        vmctl.keys(VM, 'KEY_ESC')
        wait_for(lambda: snap('mouse-closed').crop(crop).tobytes() == closed, 'Escape closes the pointer baseline')
        click(marker, 'right')
        time.sleep(.6)
        click(label(ocr(snap('items'), (230, 135, 362, 207)), 'Keyboard'))
        time.sleep(.5)
        click(label(ocr(snap('keyboard-shortcuts'), (560, 105, 835, 160)), 'None'))
        vmctl.keys(VM, *keys)
        time.sleep(1)
        pending = snap('pending')
        assert shortcut_group not in layout() and user(live) == 'a(ai) 0', 'shortcut applied before confirmation'
        click(label(ocr(pending, (760, 650, 1060, 700)), 'Apply'))
        wait_for(lambda: shortcut_group + chord in layout() and user(live) != 'a(ai) 0', 'tray shortcut saved and registered')
        print(f'Native recorder applied {chord}: {user(live)}')
        snap('applied')
        vmctl.keys(VM, 'KEY_ESC')
        vmctl.pointer(VM, 820, 690)
        wait_for(lambda: snap('before-chord').crop(crop).tobytes() == closed, 'settings dismissed before hardware chord')
        vmctl.keys(VM, *keys)
        time.sleep(.8)
        chord_opens = snap('chord-open').crop(crop).tobytes() == opened
        print(f'Hardware chord opened the pointer-identical overflow: {chord_opens}')
        if chord_opens:
            vmctl.keys(VM, *keys)
            wait_for(lambda: snap('chord-closed').crop(crop).tobytes() == closed, 'same hardware chord closes overflow')
    finally:
        print(user('/usr/bin/win7-classic current'))
    time.sleep(1)
    after = user(live)
    same_bytes = user(f'base64 -w0 {accel}') == before
    print(f'Current-mode KGlobalAccel keys: {after}; settled file byte-identical: {same_bytes}')
    print(user(f'sha256sum {accel}'))
    assert recorded == 'yes' and chord_opens and after == 'a(ai) 0' and same_bytes, 'tray shortcut round trip failed'
    vmctl.keys(VM, *keys)
    time.sleep(.6)
    assert user(live) == 'a(ai) 0', 'Windows tray action reappeared in current mode'
