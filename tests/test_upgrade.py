#!/usr/bin/env python3
"""Upgrading from the taskbar-only release (issue #13), run from the host against the lab VM.

Reproduces the reported path: install 5bfd67b, use Windows mode, upgrade while still in Windows mode, then switch.
Also checks the Start menu opens anchored above the Start button at 100% and 150% display scaling.
"""
from pathlib import Path
import sys
import time

from PIL import Image

from lab import VM, vmctl, user, toggle, close_test_apps, install, shot, wait_for

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-upgrade-test')
OLD = '5bfd67b'  # taskbar-only release, before Start menu, colors, decoration and GTK
STATE = ('cd ~/.config && sha256sum plasma-org.kde.plasma.desktop-appletsrc kdeglobals kwinrc gtk-3.0/settings.ini 2>&1; '
         'gsettings get org.gnome.desktop.interface gtk-theme; true')
FACE, DARK = (212, 208, 200), (64, 64, 64)


def output_name():
    return user('kscreen-doctor -j | python3 -c "import json,sys; print(json.load(sys.stdin)[\'outputs\'][0][\'name\'])"')


def menu_bottom_left(scale):
    """True if the Start menu's dark right edge stands directly above the taskbar at the left of the screen."""
    shot(OUT / 'probe.png')
    image = Image.open(OUT / 'probe.png').convert('RGB')
    right, top = round(404 * scale), 800 - round((44 + 461) * scale)
    edge = [image.getpixel((x, 700 - round(100 * scale))) for x in range(right - 2, right + 3)]
    return DARK in edge and image.getpixel((10, 700 - round(100 * scale))) == FACE and image.getpixel((10, top - 3)) != FACE


def check_start(scale, name):
    vmctl.pointer(VM, round(25 * scale), 800 - round(20 * scale), 'left')
    wait_for(lambda: menu_bottom_left(scale), f'Start menu above the Start button at {scale:g}x', 20)
    shot(OUT / name)
    vmctl.keys(VM, 'KEY_ESC')
    time.sleep(1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()  # normalise, then strip everything the old release didn't have
    user('rm -rf ~/.local/share/kwin/decorations/win7classic ~/.local/share/themes/Win7-Classic '
         '~/.config/fontconfig/conf.d/70-win7-classic-tahoma.conf ~/.local/state/win7-classic')
    original = user(STATE)

    install(OLD, reset=False)
    toggle('windows')
    toggle('current')
    toggle('windows')
    shot(OUT / '1-old-release-windows.png')
    print(f'old release {OLD}: in Windows mode with profiles it saved')

    install(reset=False)  # upgrade while still in Windows mode
    toggle('current')
    assert user(STATE) == original, f'current mode not restored after upgrading:\n{original}\n---\n{user(STATE)}'
    print('after upgrading: switching to current restores the original configuration exactly')

    toggle('windows')
    assert 'win7classic' in user('qdbus6 org.kde.KWin /KWin supportInformation | grep -A3 ^Decoration'), 'Classic frame not applied'
    assert user('kreadconfig6 --file kdeglobals --group KDE --key widgetStyle') == 'Windows'
    assert user('gsettings get org.gnome.desktop.interface gtk-theme') == "'Win7-Classic'"
    print('Windows mode from an old saved profile gets the new Classic frame, colors and GTK theme')
    check_start(1, '2-start-100.png')
    print('Start opens the Classic menu above the Start button')

    name = output_name()
    user(f'kscreen-doctor output.{name}.scale.1.5')
    time.sleep(3)
    try:
        check_start(1.5, '3-start-150.png')
        print('…also at 150% scaling')
    finally:
        user(f'kscreen-doctor output.{name}.scale.1')
        time.sleep(3)

    toggle('current')
    assert user(STATE) == original, 'second return to current mode differs'
    close_test_apps()
    (OUT / 'probe.png').unlink()
    print('ALL UPGRADE CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
