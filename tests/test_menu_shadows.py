#!/usr/bin/env python3
"""Compare actual KWin popup pixels outside each QWidget menu, not widget grabs (#30)."""
import argparse
from pathlib import Path
import time

from PIL import Image
from lab import ROOT, VM, activate, install, kwin_query, kwin_script, shot, toggle, user, vmctl, wait_for, windows
from test_menus import popup_bevel

KATE = 'org.kde.kate'
DOLPHIN = 'org.kde.dolphin'
EXPLORER = 'org.win7classic.explorer'
TEXT = 'unsaved compositor shadow test'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true', help='exercise the installed build (also used for the baseline)')
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    assert user('~/.local/bin/win7-classic status') == 'current'
    assert user("kscreen-doctor -j | python -c 'import json,sys; print(json.load(sys.stdin)[\"outputs\"][0][\"scale\"])'") == '1'
    root = user('mktemp -d /tmp/w7-shadow-check.XXXXXX')
    unit = root.rsplit('/', 1)[1]
    native = Image.open(ROOT / 'reference/screenshots/w7-desktop-view-submenu.png').convert('RGB')
    native.crop((235, 410, 535, 579)).save(out / 'native.png')
    white = Image.open(ROOT / 'reference/screenshots/w7-explorer-organize.png').convert('RGB')
    right = [(i, -30, white.getpixel((431 + i, 250))[0]) for i in range(8)]
    bottom = [(-30, i, white.getpixel((350, 475 + i))[0]) for i in range(8)]
    corner = [(x, y, native.getpixel((412 + x, 563 + y))[0]) for x in range(5) for y in range(5)]
    errors = []

    def key(*keys):
        vmctl.keys(VM, *('KEY_' + key for key in keys))

    def pt(x, y, button=None):
        vmctl.pointer(VM, x, y, button)

    def snap(name):
        time.sleep(.7)
        path = out / f'{name}.png'
        shot(path)
        return Image.open(path).convert('RGB')

    def start(name, cmd):
        user(f'systemd-run --user --collect -q --property=TimeoutStopSec=3s --unit={unit}-{name} {cmd}')

    def geometry(resource):
        activate(resource)
        kwin_script(f'for(const w of workspace.windowList()) if(w.resourceClass=="{resource}") '
                    '{w.frameGeometry={x:256,y:120,width:768,height:560};}')

    def checked_popup(name, open_menu):
        before = snap(name + '-underlay')
        open_menu()
        after = snap(name)
        box = popup_bevel(after)
        assert box, f'{name}: no real Classic popup frame'
        x, y, r, b = box
        assert r + 8 <= after.width and b + 8 <= after.height, (name, box)
        before.crop((x - 6, y - 6, r + 10, b + 10)).save(out / f'{name}-underlay-crop.png')
        after.crop((x - 6, y - 6, r + 10, b + 10)).save(out / f'{name}-crop.png')
        for strip, points in [('right', right), ('bottom', bottom), ('corner', corner),
                              ('left/top', [(x - r - 1, -30, 255), (-30, y - b - 1, 255)])]:
            measured = []
            for dx, dy, white in points:
                base = before.getpixel((r + dx, b + dy))
                actual = after.getpixel((r + dx, b + dy))
                expected = tuple(round(c * white / 255) for c in base)
                measured.append((expected, actual))
            error = max(abs(a - e) for expected, actual in measured for a, e in zip(actual, expected))
            print(f'{name} {strip} {box}: max error {error}; expected/actual: {measured}')
            if error > 2:
                errors.append((name, strip, error))
        return box

    def state():
        return user('cd ~/.config; sha256sum {kdeglobals,kwinrc,plasmarc,plasmashellrc,plasma-org.kde.plasma.desktop-appletsrc} 2>/dev/null; '
                    'cd ~/.local/state/win7-classic; find profiles/current -type f -print0 | sort -z | xargs -0r sha256sum')

    def pids():
        return user('pgrep -u tester -x kwin_wayland; pgrep -u tester -x kate; pgrep -u tester -x dolphin; pgrep -u tester -x win7-explorer')

    try:
        user(f'mkdir {root}/empty; : > {root}/note.txt')
        start('kate', f'kate -n {root}/note.txt')
        start('dolphin', f'dolphin --new-window {root}/empty')
        start('explorer', f'{user("echo $HOME")}/.local/bin/win7-explorer {root}/empty')
        wait_for(lambda: {KATE, DOLPHIN, EXPLORER} <= windows().keys(), 'the three live apps')
        ids = pids()
        assert len(ids.splitlines()) == 4, ids
        geometry(KATE)
        key('ESC')
        vmctl.type_text(VM, TEXT)
        wait_for(lambda: '*' in windows()[KATE][0], 'modified Kate buffer')
        key('LEFTALT', 'F')
        current = snap('kate-current-before')
        key('ESC')
        saved = state()
        (out / 'current-before.txt').write_text(saved + '\n' + ids + '\n')
        toggle('windows')
        geometry(EXPLORER)
        checked_popup('explorer-organize', lambda: pt(293, 194, 'left'))
        key('ESC')
        assert windows()[EXPLORER][1]
        geometry(DOLPHIN)
        x, _, _, b = checked_popup('dolphin-background', lambda: pt(620, 320, 'right'))
        pt(x + 60, b - 12, 'left')
        wait_for(lambda: any('Properties' in row[0] for row in kwin_query(
            'for(const w of workspace.windowList()) emit(w.caption);')), 'Dolphin Properties via the popup')
        snap('dolphin-properties')
        key('ESC')
        assert windows()[DOLPHIN][1]
        geometry(KATE)
        checked_popup('kate-file', lambda: key('LEFTALT', 'F'))
        key('ESC')
        assert windows()[KATE][1] and '*' in windows()[KATE][0]
        pt(1030, 347)
        checked_popup('plasma-desktop', lambda: pt(1030, 347, 'right'))
        key('ESC')
        toggle('current')
        assert pids() == ids and '*' in windows()[KATE][0]
        restored = state()
        (out / 'current-after.txt').write_text(restored + '\n' + pids() + '\n')
        assert restored == saved, (saved, restored)
        geometry(KATE)
        key('LEFTALT', 'F')
        after = snap('kate-current-after')
        sample = (260, 170, 550, 408)
        assert current.crop(sample).tobytes() == after.crop(sample).tobytes(), 'stock current-mode Kate menu changed'
        key('ESC')
        key('LEFTCTRL', 'S')
        assert user(f'cat {root}/note.txt') == TEXT, 'unsaved Kate text lost'
        assert not errors, f'wrong external shadow: {errors}'
        print('PASS: real Qt and Plasma QWidget shadows, action, focus, stock current pixels, profiles and running work')
    finally:
        if user('~/.local/bin/win7-classic status') != 'current':
            toggle('current')
        user(f'systemctl --user stop {unit}-{{kate,dolphin,explorer}}.service; rm -rf {root}')


if __name__ == '__main__':
    main()
