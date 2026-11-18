#!/usr/bin/env python3
"""Switch and resize a real empty Explorer view against Windows 7 (issue #41)."""
import argparse
import json
from pathlib import Path
import time

from PIL import Image

from lab import ROOT, VM, install, kwin_query, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, key

WHITE = (255, 255, 255)
NATIVE = ROOT / 'reference/screenshots'


def ink(image):
    return image.convert('L').point(lambda n: 255 if n < 140 else 0).getbbox()


def position(image, left, top, right, scale):
    center = (left + right) / 2
    half = round(75 * scale)
    start = round(center) - half
    box = ink(image.crop((start, top, start + half * 2, top + round(45 * scale))))
    assert box, f'no empty-message ink below content edge at y={top}'
    x0, y0, x1, y1 = box
    return ((start + (x0 + x1) / 2 - center) / scale, y0 / scale, (x1 - x0) / scale, (y1 - y0) / scale)


def exercise(out, scale, root):
    out.mkdir(parents=True, exist_ok=True)
    unit = f'{Path(root).name}-{round(scale * 100)}'
    exe = '~/.local/bin/win7-explorer'
    user(f'mkdir -p {root}/Classic-demo/Documents {root}/config-{scale}; '
         f'cp ~/.config/kdeglobals {root}/config-{scale}/; '
         f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={root}/config-{scale} '
         f'{exe} {root}/Classic-demo')
    place = (256, 120, 768, 560) if scale == 1 else (42, 45, 730, 405)
    x, y, w, h = place
    match = f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}")'

    def point(x, y):
        return round(x * scale), round(y * scale)

    def geometry():
        (row,) = kwin_query(match + ' { const g = w.frameGeometry; emit(g.x, g.y, g.width, g.height); }')
        return tuple(int(float(n)) for n in row)

    def view(index):
        _, _, width, _ = geometry()
        click(point(x + width - 82, y + 74))
        # The View popup has six entries. Up selects Details, Down twice selects Large Icons.
        for code in ('KEY_UP',) if index == 'details' else ('KEY_DOWN', 'KEY_DOWN'):
            key(code)
        key('KEY_ENTER')

    def snapshot(tag):
        vmctl.pointer(VM, 1180, 710)
        time.sleep(.6)
        path = out / f'{tag}.png'
        shot(path)
        with Image.open(path) as image:
            assert image.size == (1280, 800), image.size
            return image.convert('RGB')

    def content(image, mode):
        _, _, width, _ = geometry()
        left, y0 = point(x + 164, y + 90)
        right = point(x + width - 4, 0)[0]
        # Probe blank space in a column heading, not any text, divider or item.
        probe = point(x + 164 + 175, y + 102)
        assert (image.getpixel(probe) == WHITE) == (mode == 'icons'), f'expected {mode}: {probe}'
        if mode == 'details':
            top = next(row for row in range(probe[1], y0 + round(28 * scale))
                       if image.getpixel((probe[0], row)) == WHITE)
            assert abs((top - y0) / scale - 23) <= 1, (y0, top)
        else:
            top = y0
        return left, top, right

    def empty(tag, mode):
        image = snapshot(tag)
        left, top, right = content(image, mode)
        actual = position(image, left, top, right, scale)
        with Image.open(NATIVE / f'w7-explorer-empty-{mode}.png') as native:
            target = position(native, 0, 23 if mode == 'details' else 0, native.width, 1)
        print(f'{scale:g}x {tag}: content=({left},{top},{right}), '
              f'ink (center delta, gap, width, height)={actual}, native={target}', flush=True)
        assert abs(actual[0] - target[0]) <= 3, f'{tag}: empty-message not centered'
        assert abs(actual[1] - target[1]) <= 2, f'{tag}: wrong gap below content/header'
        assert abs(actual[2] - target[2]) <= 6 and abs(actual[3] - target[3]) <= 2, f'{tag}: clipped or wrong text'

    def populated(tag):
        image = snapshot(tag)
        left, top, right = content(image, 'details')
        middle = (left + right) // 2
        # Sample the start of the message, clear of the file name and Date modified cell.
        message_start = (middle - round(52 * scale), top, min(middle, left + round(272 * scale)), top + round(45 * scale))
        assert not ink(image.crop(message_start)), 'empty label survived'
        rows = image.crop((left, top, left + round(130 * scale), top + round(46 * scale)))
        assert ink(rows), 'populated Details lost its first row'
        return rows.tobytes()

    def resize(dx, dy):
        _, _, width, height = geometry()
        vmctl.pointer(VM, *point(x + width - 2, y + height - 2))
        vmctl.button(VM, 'left', True)
        try:
            vmctl.pointer(VM, *point(x + width - 2 + dx, y + height - 2 + dy))
            time.sleep(.6)
        finally:
            vmctl.button(VM, 'left', False)
        _, _, new_width, new_height = geometry()
        assert abs(new_width - width - dx) <= 2 and abs(new_height - height - dy) <= 2, (new_width, new_height)

    try:
        wait_for(lambda: 'Classic-demo' in captions(), 'production Explorer at Classic-demo')
        kwin_script(match + f' {{ w.frameGeometry = {{x:{x}, y:{y}, width:{w}, height:{h}}}; workspace.activeWindow = w; }}')
        assert geometry() == place
        click(point(x + 220, y + 150))
        key('KEY_ENTER')
        wait_for(lambda: 'Documents' in captions(), 'opened empty Documents from the icon view')
        empty('initial-icons', 'icons')
        view('details')
        empty('icons-to-details', 'details')
        resize(-120, -40)
        empty('narrow-details', 'details')
        view('icons')
        empty('details-to-icons', 'icons')
        resize(120, 40)
        empty('wider-icons', 'icons')
        view('details')
        empty('back-to-details', 'details')
        # Keep the test file's contents and inode through live model changes; never touch user data.
        user(f'printf "fixture\\n" > {root}/Sample.txt; mv {root}/Sample.txt {root}/Classic-demo/Documents/')
        time.sleep(1.5)
        rows = populated('populated-in-place')
        key('KEY_LEFTCTRL', 'KEY_E')
        vmctl.type_text(VM, 'not-a-match')
        empty('filtered-empty', 'details')
        key('KEY_LEFTCTRL', 'KEY_A')
        key('KEY_BACKSPACE')
        assert rows == populated('filter-cleared'), 'filter changed populated Details geometry'
        user(f'mv {root}/Classic-demo/Documents/Sample.txt {root}/')
        time.sleep(1.5)
        empty('last-file-removed', 'details')
        key('KEY_LEFTALT', 'KEY_LEFT')
        wait_for(lambda: 'Classic-demo' in captions(), 'Back to populated icon view')
        key('KEY_LEFTALT', 'KEY_RIGHT')
        wait_for(lambda: 'Documents' in captions(), 'Forward reopens saved empty Details view')
        empty('forward-to-details', 'details')
    finally:
        user(f'systemctl --user stop {unit} || true')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true', help='use the development Explorer already installed in the lab')
    parser.add_argument('--scales', nargs='+', type=float, choices=(1, 1.5), default=(1, 1.5))
    args = parser.parse_args()
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    initial_mode = user('~/.local/bin/win7-classic status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    root = user('mktemp -d /tmp/w7-empty.XXXXXXXX')
    try:
        toggle('current')
        toggle('windows')
        toggle('current')
        toggle('windows')
        for scale in args.scales:
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}')
            exercise(args.out / f'scale-{scale:g}', scale, root)
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}; rm -r {root}')
        toggle(initial_mode)
    print('PASS: empty view changes, content/header spacing, resizing, live file changes, filters and history')


if __name__ == '__main__':
    main()
