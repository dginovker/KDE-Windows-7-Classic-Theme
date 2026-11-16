#!/usr/bin/env python3
"""Issue #26: live portal, Dolphin and Qt folder pixels follow both mode switches."""
from pathlib import Path
import sys
import time

from PIL import Image
from lab import ROOT, VM, vmctl, user, toggle, install, shot, wait_for, kwin_query

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-icons-test')


def frames():
    return kwin_query('for (const w of workspace.windowList()) { const g = w.frameGeometry; '
                      'emit(w.resourceClass, w.caption, g.x, g.y, g.width, g.height); }')


def capture(mode):
    time.sleep(2)
    shot(OUT / f'{mode}.png')
    screen = Image.open(OUT / f'{mode}.png').convert('RGB')
    counts = {}
    for cls, title, x, y, width, height in frames():
        if title == 'Live folder icon' or cls in ('org.kde.dolphin', 'org.freedesktop.impl.portal.desktop.kde'):
            x, y, width, height = map(int, (x, y, width, height))
            crop = screen.crop((x + 5, y + 40, x + width - 5, y + height - 5))
            crop.save(OUT / f'{mode}-{cls}.png')
            yellow = sum(r > 140 and g > 100 and b < 100 and r > b * 1.4 for r, g, b in crop.getdata())
            blue = sum(b > 140 and r < 120 and b > r * 1.4 for r, g, b in crop.getdata())
            counts[title if title == 'Live folder icon' else cls] = (yellow, blue)
    assert len(counts) == 3, counts
    (OUT / f'{mode}.txt').write_text(str(counts))
    print(mode, counts, flush=True)
    for app, (yellow, blue) in counts.items():
        if mode == 'windows':
            assert yellow > 100, f'{app}: Windows folder pixels missing ({yellow}, {blue})'
        else:
            assert blue > 100 and yellow < 100, f'{app}: stale Windows folders ({yellow}, {blue})'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_icons.py'), '/tmp/fixture_icons.py')
    user('mkdir -p ~/Live-icons/Folder ~/Documents/Live-icons; chmod a+r /tmp/fixture_icons.py; '
         'systemd-run --user --collect -q python /tmp/fixture_icons.py; '
         'systemd-run --user --collect -q dolphin --new-window ~/Live-icons; '
         'systemd-run --user --collect -q gdbus call --timeout 600 --session --dest org.freedesktop.impl.portal.desktop.kde '
         '--object-path /org/freedesktop/portal/desktop --method org.freedesktop.impl.portal.FileChooser.OpenFile '
         '/org/freedesktop/portal/desktop/request/test/icons org.test.icons "" "Live portal folders" "{}"')
    wait_for(lambda: len([r for r in frames() if r[1] == 'Live folder icon' or r[0] in ('org.kde.dolphin', 'org.freedesktop.impl.portal.desktop.kde')]) == 3,
             'three long-lived icon consumers')
    # Non-overlapping windows keep each client's folder artwork observable in a single VM screenshot.
    from lab import kwin_script
    kwin_script('for (const w of workspace.windowList()) { '
                'if (w.resourceClass == "org.kde.dolphin") w.frameGeometry = {x:0,y:0,width:620,height:500}; '
                'if (w.resourceClass == "org.freedesktop.impl.portal.desktop.kde") w.frameGeometry = {x:640,y:0,width:620,height:500}; '
                'if (w.caption == "Live folder icon") w.frameGeometry = {x:400,y:520,width:200,height:180}; }')
    vmctl.pointer(VM, 1000, 300, 'left')
    for _ in range(10):
        vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_MINUS')
    for _ in range(3):
        vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_EQUAL')
    pids = user('pgrep -x dolphin; pgrep -f "^/usr/lib/xdg-desktop-portal-kde$"; pgrep -f "^/usr/bin/python /tmp/fixture_icons.py$"')
    try:
        capture('current-before')
        toggle('windows')
        capture('windows')
        toggle('current')
        capture('current-after')
        assert user('pgrep -x dolphin; pgrep -f "^/usr/lib/xdg-desktop-portal-kde$"; pgrep -f "^/usr/bin/python /tmp/fixture_icons.py$"') == pids, 'an icon consumer restarted'
        (OUT / 'pids.txt').write_text(pids)
        print('ALL LIVE ICON CHECKS PASSED; unchanged PIDs:', pids)
    finally:
        toggle('current')
        user('pkill -f "^/usr/bin/python /tmp/fixture_icons.py$"; pkill -x dolphin; true')
        vmctl.keys(VM, 'KEY_ESC')


if __name__ == '__main__':
    main()
