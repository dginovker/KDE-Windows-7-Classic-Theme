#!/usr/bin/env python3
"""Native structural control pixels through the actual desktop style, not mocked QPalette roles (#28)."""
from pathlib import Path
import json
import sys
import time
import xml.etree.ElementTree as ET
from PIL import Image, ImageChops
from lab import ROOT, VM, vmctl, install, toggle, user, shot, wait_for
import test_frames as frames

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-classic-widgets-test')
REF = ROOT / 'reference/screenshots/controls-native-client.png'


def assert_pixels(ours, name, box, masks=()):
    native = Image.open(REF).convert('RGB')
    bad = [(x, y, ours.getpixel((x, y)), native.getpixel((x, y)))
           for y in range(box[1], box[3]) for x in range(box[0], box[2])
           if not any(l <= x < r and t <= y < b for l, t, r, b in masks)
           and ours.getpixel((x, y)) != native.getpixel((x, y))]
    ours.crop(box).save(OUT / f'{name}-ours.png')
    native.crop(box).save(OUT / f'{name}-native.png')
    ImageChops.difference(ours.crop(box), native.crop(box)).point(lambda v: 255 if v else 0).save(OUT / f'{name}-diff.png')
    assert not bad, f'{name}: {len(bad)} structural pixels differ: {bad[:8]}'
    print(name, 'matches native structure')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    frames.start_fixture()  # Already-running widgets must acquire the new style, not just new processes.
    wait_for(lambda: user('test -f /tmp/fixture-palette.json && echo ready') == 'ready', 'current palette report')
    before = json.loads(user('cat /tmp/fixture-palette.json'))
    (OUT / 'current-before.json').write_text(json.dumps(before, indent=2))
    toggle('windows')
    frames.fixture((140, 100, 1000, 560))
    vmctl.pointer(VM, 1200, 700)
    time.sleep(2)
    probe = json.loads(user('systemd-run --user --wait --pipe --collect -q ~/.local/bin/win7-classic-probe'))
    (OUT / 'manifest.json').write_text(json.dumps(probe, indent=2))
    assert probe['style'].lower() == 'win7classic'
    live = json.loads(user('cat /tmp/fixture-palette.json'))
    (OUT / 'live-palette.json').write_text(json.dumps(live, indent=2))
    assert live['style'].lower() == 'win7classic'
    for name in ('app', 'combo', 'scroll', 'group'):
        for group, index in [('Active', '0'), ('Inactive', '2'), ('Disabled', '1')]:
            assert live[name][group] == probe['palette'][index], (name, group, live[name][group])
    for group in probe['palette'].values():
        assert {r: group[r] for r in ('Button', 'Light', 'Midlight', 'Dark', 'Shadow')} == {
            'Button': '#d4d0c8', 'Light': '#ffffff', 'Midlight': '#d4d0c8', 'Dark': '#808080', 'Shadow': '#404040'}
    panel = ET.parse(ROOT / 'plasma/theme/win7-classic/widgets/panel-background.svg').getroot()
    for side in ('top', 'topleft', 'topright'):
        rows = next(e for e in panel if e.get('id') == side)
        assert [row.get('fill') for row in rows] == [probe['palette']['0']['Button'], probe['palette']['0']['Light']]
        assert [row.get('y') for row in rows] == ['0', '1']
    assert probe['palette']['1']['Base'] == '#d4d0c8'   # QPalette::Disabled
    shot(OUT / 'widgets.png')
    ours = Image.open(OUT / 'widgets.png').convert('RGB').crop((144, 123, 1136, 656))
    for name, x in [('normal', 24), ('pressed', 174), ('disabled', 324), ('focused', 474), ('default', 624)]:
        # Only label ink is excluded; all face, bevel, default and focus pixels remain asserted.
        assert_pixels(ours, name, (x, 65, x + 130, 91), [(x + 40, 72, x + 94, 86)])
    for name, x in [('check', 24), ('checked', 190), ('disabled-checked', 356)]:
        assert_pixels(ours, name, (x, 125, x + 13, 138))
    for name, x in [('radio', 24), ('selected-radio', 190)]:
        assert_pixels(ours, name, (x, 167, x + 13, 180))
    assert_pixels(ours, 'flat-edit', (24, 215, 304, 239), [(27, 218, 150, 236)])
    assert_pixels(ours, 'disabled-edit', (324, 215, 604, 239), [(327, 218, 450, 236)])
    assert_pixels(ours, 'combo', (24, 265, 304, 286), [(27, 268, 150, 283)])
    assert_pixels(ours, 'combo-arrow', (286, 267, 302, 284))
    assert_pixels(ours, 'group-box', (24, 330, 604, 450), [(31, 330, 100, 345), (44, 368, 400, 392)])
    for group in ('0', '1', '2'):
        assert probe['palette'][group]['Window'] == '#d4d0c8'
    toggle('current')
    time.sleep(1)
    restored = json.loads(user('cat /tmp/fixture-palette.json'))
    (OUT / 'current-after.json').write_text(json.dumps(restored, indent=2))
    assert restored == before, 'live widget palettes did not restore exactly'
    toggle('windows')
    user('pkill -f "^/usr/bin/python3 /tmp/fixture_window.py"; true')
    user('systemd-run --user --collect -q python3 /tmp/fixture_window.py --dialog')
    wait_for(lambda: frames.fixture_state() != 'gone', 'real QDialog default case')
    frames.fixture((140, 100, 1000, 560))
    time.sleep(1)
    shot(OUT / 'dialog.png')
    dialog = Image.open(OUT / 'dialog.png').convert('RGB').crop((144, 123, 1136, 656))
    assert_pixels(dialog, 'dialog-default', (624, 65, 754, 91), [(664, 72, 718, 86)])
    user('pkill -f "^/usr/bin/python3 /tmp/fixture_window.py"; true')
    toggle('current')
    print('ALL CLASSIC WIDGET CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
