#!/usr/bin/env python3
"""Drive the real address bar at 100%/150%, including navigation history."""
import argparse
from pathlib import Path
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, executable, explorer_identity, install, kwin_query, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, key
from test_upgrade import output_name


def asset(name, pixels):
    sizes = {'folder': (16, 32), 'downloads': (16, 24)}
    source = sizes[name][pixels != 16]
    return Image.open(ROOT / f'explorer/assets/{name}-{source}.png').convert('RGBA').resize((pixels, pixels), Image.Resampling.LANCZOS)


def against(actual, icon):
    expected = Image.new('RGBA', actual.size, (212, 208, 200))
    expected.alpha_composite(icon)
    errors = ImageChops.difference(actual, expected.convert('RGB')).get_flattened_data()
    return sum(sum(rgb) for rgb in errors) / (actual.width * actual.height * 3)


def run(out, scale, reference, ordinary, packaged):
    x, y = (256, 120) if scale == 1 else (42, 44)
    assert not captions(), "close any existing Explorer windows before testing"
    exe = executable("win7-explorer", packaged)
    user(f'systemd-run --user --collect -q {exe} {ordinary}')
    downloads = user('xdg-user-dir DOWNLOAD')
    wait_for(lambda: 'Ordinary' in captions(), 'ordinary folder opened')
    kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" && w.caption == "Ordinary") '
                f'{{ w.frameGeometry={{x:{x},y:{y},width:768,height:405}}; workspace.activeWindow=w; }}')

    def open_windows():
        return kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}") '
                          'emit(w.pid, w.internalId, w.caption, w.active, w.frameGeometry.x, w.frameGeometry.y);')

    [(pid, ident, _, _, _, _)] = open_windows()
    explorer_identity(pid, exe, out)
    slots = {}

    def pt(a, b):
        return round((x + a) * scale), round((y + b) * scale)

    def capture(name, expected):
        caption = Path(downloads).name if expected == 'downloads' else 'Ordinary'
        wait_for(lambda: caption in captions(), caption)
        assert open_windows() == [[pid, ident, caption, 'true', str(x), str(y)]]
        vmctl.pointer(VM, 5, 560)
        time.sleep(.5)
        path = out / f'{name}.png'
        shot(path)
        # At 150%, KWin rounds the frame inset separately: the slot starts 49 device rows below y=66.
        sx, sy = pt(4 + 74 + 2, 23 + 9)
        if scale == 1.5:
            sy += 1
        pixels = round(16 * scale)
        actual = Image.open(path).convert('RGB').crop((sx, sy, sx + pixels, sy + pixels))
        actual.save(out / f'{name}-slot.png')
        slots[name] = actual, expected

    def compare_slots():
        failures = []
        for name, (actual, expected) in slots.items():
            pixels = actual.width
            other = 'downloads' if expected == 'folder' else 'folder'
            match, opposite = [against(actual, asset(icon, pixels)) for icon in (expected, other)]
            # At 150% Downloads has native 24px art; ordinary is resampled by Qt.
            limit = 0.1 if expected == 'downloads' else (4 if scale == 1 else 6)
            print(f'{name}: {pixels}x{pixels}, {expected} delta={match:.4f}, {other} delta={opposite:.4f}', flush=True)
            if match > limit or match + 8 >= opposite:
                failures.append(f'{name}: expected {expected} art')
        if scale == 1:
            native = Image.open(reference).convert('RGBA')
            assert native.size == (408, 32), 'expected the issue’s genuine 96-DPI address-band attachment'
            native = native.crop((4, 6, 20, 22))
            native.save(out / 'native-downloads-slot.png')
            for name in ('downloads', 'forward'):
                delta = against(slots[name][0], native)
                print(f'{name}: attachment 96-DPI mean channel delta={delta:.4f}', flush=True)
                if delta:
                    failures.append(f'{name}: slot differs from the genuine attachment')
        return failures

    try:
        capture('ordinary', 'folder')
        click(pt(65, 143))  # Favorites > Downloads
        capture('downloads', 'downloads')
        click(pt(21, 42))
        capture('back', 'folder')
        click(pt(49, 42))
        capture('forward', 'downloads')
        key('KEY_LEFTALT', 'KEY_D')
        vmctl.type_text(VM, ordinary + '\n')
        capture('address-entry', 'folder')
        # Preserve main's editor click dispatch, including the overlapping painted targets.
        for name, point in [('empty-address', (400, 42)), ('places-arrow', (108, 42)), ('home-crumb', (123, 40))]:
            click(pt(*point))
            shot(out / f'{name}-editor.png')
            vmctl.type_text(VM, downloads + '\n')
            wait_for(lambda: captions() == [Path(downloads).name], f'{name} click edits the address')
            click(pt(21, 42))
            wait_for(lambda: captions() == ['Ordinary'], f'Back after {name} address entry')
            print(f'{name}: click-to-edit navigated to Downloads; Back returned to Ordinary', flush=True)
        failures = compare_slots()
        assert not failures, failures
        print('PASS address slot, history and unchanged mouse/keyboard address entry', flush=True)
    finally:
        key('KEY_LEFTALT', 'KEY_F4')
        wait_for(lambda: not captions(), 'fixture Explorer closed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('native_downloads', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    choices = parser.add_mutually_exclusive_group()
    choices.add_argument('--installed', action='store_true')
    choices.add_argument('--packaged', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not (args.installed or args.packaged):
        install(reset=False)
    output = output_name()
    toggle('current', packaged=args.packaged)
    base = '/home/tester/w7-address-test'
    user(f'mkdir {base} && mkdir {base}/Ordinary')
    try:
        user(f'kscreen-doctor output.{output}.scale.{args.scale}')
        toggle('windows', packaged=args.packaged)
        run(args.out, args.scale, args.native_downloads, f'{base}/Ordinary', args.packaged)
    finally:
        user(f'rmdir {base}/Ordinary {base}')
        toggle('current', packaged=args.packaged)
        user(f'kscreen-doctor output.{output}.scale.1')


if __name__ == '__main__':
    main()
