#!/usr/bin/env python3
"""Windows-mode lock screen (issue #15), with the tester account's real password, against the lab VM.

Wrong password is rejected and the session stays locked; the right one unlocks. Current mode keeps Plasma's own
lock screen. A broken lock screen must still be unlockable (kscreenlocker's built-in fallback).
"""
from pathlib import Path
import sys
import time

from PIL import Image

from lab import ROOT, VM, vmctl, user, toggle, install, shot, wait_for

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-lock-test')
PASSWORD = 'win7-test-pass'  # set by vm/prepare-tester.sh
REF = ROOT / 'reference/screenshots/w7-lock.png'
OVERLAY = '~/.local/share/plasma/shells/org.kde.plasma.desktop'


def locked():
    return user('qdbus6 org.freedesktop.ScreenSaver /ScreenSaver GetActive') == 'true'


def white_bands(path):
    """Vertical extents of white elements in the centre column (name, subtitle, password field, button text)."""
    image = Image.open(path).convert('RGB')
    rows = [y for y in range(430, 620) if sum(1 for x in range(520, 760) if min(image.getpixel((x, y))) > 235) > 3]
    bands, start = [], None
    for i, y in enumerate(rows):
        start = y if start is None else start
        if i + 1 == len(rows) or rows[i + 1] != y + 1:
            bands.append((start, y))
            start = None
    return bands


def field_band(path):
    return next((b for b in white_bands(path) if b[1] - b[0] >= 15 and b[0] > 485), None)


def lock(name):
    user('qdbus6 org.freedesktop.ScreenSaver /ScreenSaver Lock')
    wait_for(locked, 'screen locked')
    time.sleep(2)
    vmctl.pointer(VM, 600, 420)  # wake the greeter UI
    vmctl.pointer(VM, 610, 430)
    time.sleep(2)
    shot(OUT / name)


def type_password(password):
    vmctl.type_text(VM, password)
    vmctl.keys(VM, 'KEY_ENTER')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    vmctl.start(VM)
    install()
    toggle('windows')

    lock('1-windows-locked.png')
    ours, reference = field_band(OUT / '1-windows-locked.png'), field_band(REF)
    assert ours and abs(ours[0] - reference[0]) <= 2 and abs(ours[1] - reference[1]) <= 2, f'password field rows {ours}, Windows {reference}'
    tile = Image.open(OUT / '1-windows-locked.png').convert('RGB').getpixel((636, 276))
    assert min(tile) > 200, f'no light user-tile frame at the reference position: {tile}'
    print(f'Classic lock screen: user tile and password field where Windows has them (field rows {ours}, Windows {reference})')

    type_password('wrong-password')
    time.sleep(4)
    shot(OUT / '2-wrong-password.png')
    assert locked(), 'a wrong password unlocked the session'
    assert field_band(OUT / '2-wrong-password.png') is None, 'no error shown after a wrong password'
    print('wrong password: error shown, still locked')

    vmctl.keys(VM, 'KEY_ENTER')  # OK
    time.sleep(1)
    type_password(PASSWORD)
    wait_for(lambda: not locked(), 'right password unlocks', 20)
    print('right password unlocks')

    toggle('current')
    assert user(f'test -e {OVERLAY} && echo present || echo gone') == 'gone', 'lock screen overlay left behind in current mode'
    lock('3-current-locked.png')
    assert field_band(OUT / '3-current-locked.png') != field_band(OUT / '1-windows-locked.png'), 'current mode shows the Classic lock screen'
    type_password(PASSWORD)
    wait_for(lambda: not locked(), 'current mode unlocks with the password', 20)
    print("current mode keeps Plasma's lock screen and unlocks")

    toggle('windows')
    user(f'echo "this is not QML" >> {OVERLAY}/contents/lockscreen/LogonUi.qml')
    lock('4-broken-theme.png')
    assert field_band(OUT / '4-broken-theme.png') is None, 'broken Windows UI still drew its password field'
    type_password('wrong-password')
    time.sleep(4)
    assert locked(), 'a wrong password unlocked the plain fallback'
    type_password(PASSWORD)
    wait_for(lambda: not locked(), 'unlocking still works with a broken lock screen theme', 20)
    print('a broken Windows lock screen falls back to a plain password field that rejects wrong and accepts right')
    toggle('current')
    print('ALL LOCK CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
