#!/usr/bin/env python3
"""Drive a real libappindicator and live SNI menu/tooltip changes in the packaged tray."""
from pathlib import Path
import shlex
import sys
import time

from PIL import Image

from lab import ROOT, VM, shot, user, vmctl, wait_for
from test_tray import REFERENCE, icon_center, label, ocr

PREFIX = '/tmp/w39-notifier'
IND = "w39-tray-appindicator-" + str(time.monotonic_ns())
DETAILS = "w39-tray-details-" + str(time.monotonic_ns())
PIXMAP = (37, 191, 237)


def main(out, case):
    out.mkdir(parents=True, exist_ok=True)
    assert user('/usr/bin/win7-classic status') == 'windows'
    ref = Image.open(REFERENCE).convert('RGB')

    def snap(name):
        path = out / (name + '.png')
        shot(path)
        return Image.open(path).convert('RGB')

    def words(name, box=(1060, 723, 1215, 760)):
        return ocr(snap(name), box)

    def click(point, button='left'):
        vmctl.pointer(VM, *point, button)

    def includes(name, *expected):
        box = (1027, 706, 1137, 755) if name.startswith('tooltip') else (1060, 723, 1215, 760)
        return set(expected) <= {word for word, _ in words(name, box)}

    def log(unit):
        return user(f'journalctl --user -b -u {unit} --since "{since}" -o cat --no-pager')

    since = user('date -Is')
    try:
        if case == 'appindicator':
            user(f"printf %s {shlex.quote((ROOT / 'tests/fixtures/tray_appindicator.c').read_text())} > {PREFIX}.c")
            user(f'cc {PREFIX}.c -o {PREFIX} $(pkg-config --cflags --libs appindicator3-0.1) && '
                 f'systemd-run --user --collect --unit={IND} {PREFIX}')
            wait_for(lambda: 'w39_appindicator' in user('busctl --user get-property org.kde.StatusNotifierWatcher '
                     '/StatusNotifierWatcher org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems'),
                     'real libappindicator registers')
            listings = user('busctl --user get-property org.kde.StatusNotifierWatcher /StatusNotifierWatcher '
                            'org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems')
            item, = [entry for entry in listings.split('"')[1::2] if entry.endswith('/w39_appindicator')]
            service, path = item.split('/', 1)
            protocol = user(f'busctl --user introspect {service} /{path} org.kde.StatusNotifierItem')
            print(protocol)
            assert '.Activate ' not in protocol and '.ItemIsMenu' not in protocol and '.Menu ' in protocol
            time.sleep(.5)
            x, y = icon_center(snap('indicator-idle'), ref, (13, 17, 18, 25))
            vmctl.pointer(VM, x + 22, y)
            click((x + 22, y))
            wait_for(lambda: includes('indicator-menu', 'Indicator', 'Action'), 'primary click opens real AppIndicator menu')
            click(label(words('indicator-action'), 'Action'))
            wait_for(lambda: 'Clicked actual AppIndicator menu action' in log(IND), 'GTK callback receives menu action')
            print(log(IND))
        else:
            user(f"printf %s {shlex.quote((ROOT / 'tests/fixtures/tray_details_sni.py').read_text())} > {PREFIX}.py")
            user(f'rm -f {PREFIX}.state; systemd-run --user --collect --unit={DETAILS} python {PREFIX}.py {PREFIX}.state')
            wait_for(lambda: 'Registered ' in log(DETAILS), 'live item registered')
            time.sleep(.5)
            idle = snap('detail-idle')
            points = [(x, y) for x in range(950, 1210) for y in range(763, 794) if idle.getpixel((x, y)) == PIXMAP]
            assert len(points) == 22 * 22, len(points)
            pt = tuple((min(p[n] for p in points) + max(p[n] for p in points)) // 2 for n in (0, 1))
            if case == 'tooltip':
                vmctl.pointer(VM, *pt)
                wait_for(lambda: includes('tooltip-initial', 'Device', 'Details', 'Initial', 'Battery'),
                         'actual tooltip contains both producer fields')
                user(f'echo tooltip > {PREFIX}.state')
                wait_for(lambda: 'Updated tooltip' in log(DETAILS), 'producer emits NewToolTip')
                wait_for(lambda: includes('tooltip-updated', 'Device', 'Details', 'Updated', 'Battery'),
                         'still-hovered tooltip updates subtitle')
            else:
                click(pt)
                wait_for(lambda: '\nActivate' in log(DETAILS), 'a menu-capable item with Activate still activates on primary')
                click(pt, 'right')
                wait_for(lambda: includes('initial-menu', 'Initial', 'Action'), 'original menu opens')
                vmctl.keys(VM, 'KEY_ESC')
                user(f'echo menu > {PREFIX}.state')
                wait_for(lambda: 'Updated menu path' in log(DETAILS), 'producer emits NewMenu only')
                click(pt, 'right')
                wait_for(lambda: includes('updated-menu', 'Updated', 'Action'), 'new menu opens instead of stale menu')
                click(label(words('updated-action'), 'Action'))
                wait_for(lambda: "/Updated Event (1, 'clicked'" in log(DETAILS), 'action comes from replacement path')
            print(log(DETAILS))
    finally:
        user(f'systemctl --user stop {IND if case == "appindicator" else DETAILS} || :; rm -f {PREFIX} {PREFIX}.c {PREFIX}.py {PREFIX}.state')
        vmctl.pointer(VM, 820, 540, 'left')


if __name__ == '__main__':
    assert sys.argv[2] in ('appindicator', 'tooltip', 'menu')
    main(Path(sys.argv[1]), sys.argv[2])
