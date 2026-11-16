#!/usr/bin/env python3
"""Issue #27: genuine cursor pixels in a running Wayland session, and live Breeze restoration."""
from contextlib import contextmanager
from pathlib import Path
import runpy
import sys
import time

from PIL import Image, ImageChops
from lab import ROOT, VM, vmctl, user, toggle, install, shot, wait_for, windows, kwin_script, kwin_query

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-cursors-test')
SOURCE = runpy.run_path(str(ROOT / 'reference/tools/extract-cursors.py'))
POINTS = {'desktop': (1000, 550), 'white': (200, 220), 'dark': (550, 220)}


def image(name):
    variants = SOURCE['cur_images']((ROOT / 'reference/cursors' / name).read_bytes())
    return next((im, hx, hy) for im, hx, hy in variants if im.width == 32)


def capture(mode):
    result = {}
    for surface, (x, y) in POINTS.items():
        vmctl.pointer(VM, 1100, 650)
        time.sleep(.4)
        shot(OUT / f'{mode}-{surface}-background.png')
        background = Image.open(OUT / f'{mode}-{surface}-background.png').convert('RGBA')
        vmctl.pointer(VM, x, y)
        time.sleep(.4)
        x, y = map(int, kwin_query('emit(workspace.cursorPos.x, workspace.cursorPos.y);')[0])
        shot(OUT / f'{mode}-{surface}.png')
        actual = Image.open(OUT / f'{mode}-{surface}.png').convert('RGBA')
        result[surface] = actual.crop((x - 16, y - 16, x + 48, y + 48))
        if mode == 'windows':
            cursor, hx, hy = image('aero_arrow.cur' if surface == 'desktop' else 'user32-ibeam.cur')
            expected = background.copy()
            expected.alpha_composite(cursor, (x - hx, y - hy))
            box = (x - hx, y - hy, x - hx + 32, y - hy + 32)
            diff = ImageChops.difference(actual.crop(box).convert('RGB'), expected.crop(box).convert('RGB'))
            error = max(high for low, high in diff.getextrema())
            assert error <= 1, f'{surface}: genuine cursor pixel error {error}; see {OUT}/{mode}-{surface}.png'
            if surface == 'dark':
                assert sum(r > 240 and g > 240 and b > 240 for r, g, b, a in actual.crop(box).getdata()) > 20, 'I-beam invisible over dark field'
            print(f'{surface}: genuine cursor composite max error {error}', flush=True)
    return result


def restart_session():
    code, out, err = vmctl.run(VM, 'loginctl terminate-user tester; sleep 3; systemctl restart sddm', 30)
    assert code == 0, out + err
    time.sleep(10)
    vmctl.start(VM)


@contextmanager
def software_cursor():
    # QEMU screendump omits the virtio hardware cursor, so test the same KWin renderer in software.
    config = '~/.config/environment.d/90-win7-test-sw-cursor.conf'
    user(f'set -e; test ! -e {config}; mkdir -p ~/.config/environment.d; printf "KWIN_FORCE_SW_CURSOR=1\\n" > {config}')
    try:
        restart_session()
        code, out, err = vmctl.run(VM, 'tr "\\0" "\\n" < /proc/$(pgrep -x kwin_wayland)/environ | grep -x KWIN_FORCE_SW_CURSOR=1', 10)
        assert code == 0, 'software cursor instrumentation did not reach KWin: ' + out + err
        yield
    finally:
        user(f'rm {config}')
        restart_session()
        code, _, _ = vmctl.run(VM, 'tr "\\0" "\\n" < /proc/$(pgrep -x kwin_wayland)/environ | grep -q KWIN_FORCE_SW_CURSOR=', 10)
        assert code == 1, 'software cursor test instrumentation remains active'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_cursors.py'), '/tmp/fixture_cursors.py')
    user('chmod a+r /tmp/fixture_cursors.py; systemd-run --user --collect -q python /tmp/fixture_cursors.py')
    wait_for(lambda: 'python' in windows(), 'cursor text fields')
    kwin_script('for (const w of workspace.windowList()) if (w.caption == "Live cursor fields") '
                '{ w.frameGeometry = {x:80,y:100,width:700,height:330}; workspace.activeWindow = w; }')
    pids = user('pgrep -x kwin_wayland; pgrep -f "^/usr/bin/python /tmp/fixture_cursors.py$"')
    baseline = capture('current-before')
    try:
        toggle('windows')
        capture('windows')
        assert user('kreadconfig6 --file kcminputrc --group Mouse --key cursorTheme') == 'Win7-Classic-Cursors'
        wait_for(lambda: user('gsettings get org.gnome.desktop.interface cursor-theme') == "'Win7-Classic-Cursors'", 'GTK cursor theme')
        assert user('gsettings get org.gnome.desktop.interface cursor-size') == '32'
        # Both animated cursor roles must visibly advance without moving the pointer.
        for role, point in (('wait', (200, 340)), ('progress', (550, 340))):
            vmctl.pointer(VM, *point)
            crops = set()
            for i in range(6):
                shot(OUT / f'{role}-{i}.png')
                x, y = point
                crops.add(Image.open(OUT / f'{role}-{i}.png').crop((x - 16, y - 16, x + 48, y + 48)).tobytes())
                time.sleep(.07)
            assert len(crops) > 1, f'{role} cursor did not animate'
        toggle('current')
        restored = capture('current-after')
        for surface in ('white', 'dark'):
            assert ImageChops.difference(baseline[surface], restored[surface]).convert('RGB').getbbox() is None, f'Breeze {surface} cursor not restored'
        wait_for(lambda: user('gsettings get org.gnome.desktop.interface cursor-theme') == "'breeze_cursors'", 'GTK Breeze cursor')
        assert user('pgrep -x kwin_wayland; pgrep -f "^/usr/bin/python /tmp/fixture_cursors.py$"') == pids, 'KWin or text-field app restarted'
        (OUT / 'pids.txt').write_text(pids)
        print('ALL CURSOR CHECKS PASSED; unchanged KWin/application PIDs:', pids)
    finally:
        toggle('current')
        user('pkill -f "^/usr/bin/python /tmp/fixture_cursors.py$"; true')


if __name__ == '__main__':
    vmctl.start(VM)
    with software_cursor():
        main()
