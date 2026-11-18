#!/usr/bin/env python3
"""Drive KDE's folder Properties from Explorer without changing any real files (#38)."""
import argparse
import json
from pathlib import Path

from PIL import Image

from lab import ROOT, VM, install, kwin_query, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, key


def check_general(image, scale, native=False):
    # Compare chrome, not labels (KDE has additional data/widgets in the same groups).
    width, height = (n / scale for n in image.size)
    assert 360 <= width <= 415 and 460 <= height <= 525, (width, height)
    left = round((17 if native else 15) * scale)
    bands = []
    center = image.width // 2
    for y in range(round(84 * scale), image.height - round(48 * scale)):
        if all(image.getpixel((x, y)) == (128, 128, 128) for x in (left + round(20 * scale), center, image.width - round(32 * scale))):
            if not bands or y > bands[-1][-1] + 1:
                bands.append([])
            bands[-1].append(y)
    assert len(bands) == 3, (scale, bands)
    assert 92 <= bands[0][0] / scale <= 108, (scale, bands)
    assert any(image.getpixel((center, y)) == (64, 64, 64)
               for y in range(image.height - round(44 * scale), image.height - round(34 * scale))), 'missing page surround'
    print(f'{scale:g}x {"Windows 7" if native else "Explorer"}: {width:g}×{height:g} logical; three etched groups', flush=True)


def active_frame():
    rows = kwin_query('for (const w of workspace.windowList()) if (workspace.activeWindow === w) '
                      'emit(w.caption, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height);')
    assert len(rows) == 1, rows
    return rows[0][0], tuple(map(float, rows[0][1:]))


def exercise(out, scale):
    out.mkdir(parents=True, exist_ok=True)
    root = user('mktemp -d /tmp/w7prop.XXXXXXXX')
    unit = Path(root).name
    folder = f'{root}/Classic-demo'
    try:
        user(f'mkdir -p {folder}/Documents; chmod 755 {folder}/Documents; '
             f'systemd-run --user --collect -q --unit={unit} ~/.local/bin/win7-explorer {folder}')
        wait_for(lambda: 'Classic-demo' in captions(), 'Explorer fixture')
        kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}") {{ '
                    'w.frameGeometry = {x: 42, y: 32, width: 734, height: 443}; workspace.activeWindow = w; }')

        def open_properties():
            click((round(260 * scale), round(178 * scale)))
            key('KEY_LEFTALT', 'KEY_ENTER')
            wait_for(lambda: active_frame()[0] == 'Properties for Documents', 'folder Properties')
            return active_frame()[1]

        def capture(tag):
            vmctl.pointer(VM, 1220, 700)
            path = out / f'{tag}-desktop.png'
            shot(path)
            title, (x, y, w, h) = active_frame()
            assert title == 'Properties for Documents', title
            image = Image.open(path).convert('RGB').crop(tuple(round(n * scale) for n in (x, y, x+w, y+h)))
            image.save(out / f'{tag}.png')
            return image

        def at(x, y):
            click((round((frame[0]+x) * scale), round((frame[1]+y) * scale)))

        def edit(name):
            at(150, 73)
            key('KEY_LEFTCTRL', 'KEY_A')
            vmctl.type_text(VM, name)

        def state():
            return user(f'find {folder} -mindepth 1 -printf "%P %m\\n"')

        frame = open_properties()
        check_general(capture('general'), scale)
        if scale == 1:
            at(107, 37)
            capture('permissions')
            at(178, 37)
            capture('details')
            at(36, 37)
        edit('Discarded')
        assert state() == 'Documents 755', state()
        at(frame[2] - 47, frame[3] - 23)
        wait_for(lambda: active_frame()[0] == 'Classic-demo', 'Cancel to close')
        assert state() == 'Documents 755', state()
        frame = open_properties()
        edit('Saved')
        assert state() == 'Documents 755', state()
        at(frame[2] - 130, frame[3] - 23)
        wait_for(lambda: active_frame()[0] == 'Classic-demo' and state() == 'Saved 755', 'KIO to save and close')
        print(f'{scale:g}x edit remained pending; Cancel discarded it, OK committed it and closed', flush=True)
    finally:
        user(f'systemctl --user stop {unit}; rm -r {root}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--baseline', type=Path, help='apply the same visual checks to a cropped baseline (expected failure)')
    args = parser.parse_args()
    if args.baseline:
        check_general(Image.open(args.baseline).convert('RGB'), 1)
        return
    native = Image.open(ROOT / 'reference/screenshots/w7-properties.png').convert('RGB').crop((470, 250, 837, 724))
    check_general(native, 1, native=True)
    vmctl.start(VM)
    if not args.installed:
        install()
        toggle('windows')
    output, = json.loads(user('kscreen-doctor -j'))['outputs']
    try:
        for scale in (1, 1.5):
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}')
            exercise(args.out / f'scale-{scale:g}', scale)
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}')


if __name__ == '__main__':
    main()
