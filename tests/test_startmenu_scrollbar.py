#!/usr/bin/env python3
"""Drive All Programs overflow on a stock 1280x800 lab panel, without resetting either profile (#58)."""
import argparse
from contextlib import contextmanager
from itertools import groupby
import json
from pathlib import Path
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, executable, install, shot, toggle, user, vmctl, wait_for

OVERFLOW, FIT = 48, 20
FACE, BLUE = (212, 208, 200), (10, 36, 106)
NATIVE = ROOT / 'reference/screenshots/w7-programs-overflow.png'


@contextmanager
def launchers():
    base = Path(user('mktemp -d /tmp/w7-program-scroll.XXXXXXXX'))
    stem = base.name
    merged = f'~/.config/menus/applications-merged/{stem}.menu'
    dirs = f'~/.local/share/desktop-directories/{stem}'
    apps = f'~/.local/share/applications/{stem}'
    commands = [f'cat > {merged} <<\'EOF\'', '<Menu><Name>Applications</Name>']
    files = [merged]
    entries = []
    for group, count in [('AAA', OVERFLOW), ('AAB', FIT)]:
        directory = f'{dirs}-{group}.directory'
        files.append(directory)
        commands += [f'<Menu><Name>{group}-{stem}</Name><Directory>{Path(directory).name}</Directory><Include>']
        entries += [f"cat > {directory} <<'EOF'", '[Desktop Entry]', 'Type=Directory',
                    f'Name={group} W7 Scroll QA', 'Icon=applications-development', 'EOF']
        for row in range(1, count + 1):
            entry = f'{apps}-{group}-{row:02}.desktop'
            files.append(entry)
            commands.append(f'<Filename>{Path(entry).name}</Filename>')
            entries += [f"cat > {entry} <<'EOF'", '[Desktop Entry]', 'Type=Application',
                        f'Name=W7 Scroll QA {group} {row:02}', 'Icon=utilities-terminal',
                        f'Exec=/usr/bin/touch {base}/{group}-{row:02}', 'EOF']
        commands.append('</Include></Menu>')
    commands += ['</Menu>', 'EOF']
    user('test ! -e ' + ' && test ! -e '.join(files))
    try:
        user('\n'.join(['set -euC', 'mkdir -p ~/.config/menus/applications-merged '
                        '~/.local/share/{desktop-directories,applications}', *commands, *entries, 'kbuildsycoca6']))
        yield base, 'sha256sum ' + ' '.join(files)
    finally:
        user(f'rm -f {" ".join(files)}; rm -rf {base}; kbuildsycoca6')


def key(name):
    vmctl.keys(VM, 'KEY_' + name)


def snap(out, name):
    time.sleep(.45)
    path = out / f'{name}.png'
    shot(path)
    with Image.open(path) as image:
        assert image.size == (1280, 800), image.size
        return image.convert('RGB')


def expect_launch(base, expected):
    names = lambda: user(f'ls -1 {base}')
    wait_for(names, f'launch marker for {expected}')
    actual = names()
    assert actual == expected, f'Wrong desktop entry: expected {expected}, got {actual!r}'
    user(f'rm {base}/{expected}')
    print(f'Launched {expected}', flush=True)


def exercise(out, scale, base):
    top = 800 - round(505 * scale)

    def pt(x, y):
        return round(x * scale), top + round(y * scale)

    def pointer(x, y, press=None):
        vmctl.pointer(VM, *pt(x, y), press)

    def park():
        vmctl.pointer(VM, 640, 700)

    def click(x, y):
        pointer(x, y, 'left')
        park()

    def open_programs():
        key('LEFTMETA')
        time.sleep(.5)
        click(85, 407)

    def open_group():
        open_programs()
        click(70, 14)

    def rail(name):
        image = snap(out, name)
        crop = image.crop((*pt(237, 3), *pt(253, 381)))
        crop.save(out / f'{name}-rail.png')
        return crop

    def thumb(strip):
        # The thumb, unlike the stipple, has a contiguous face across its inner columns.
        s = round(16 * scale)
        ys = [y for y in range(s, strip.height - s)
              if all(strip.getpixel((x, y)) == FACE for x in range(round(3 * scale), round(13 * scale)))]
        # The outer top rim uses the face color too, but a white rim separates it from the face.
        runs = ([y for _, y in run] for _, run in groupby(enumerate(ys), key=lambda pair: pair[1] - pair[0]))
        body = max(runs, key=len, default=[])
        assert len(body) > 2, 'Missing scrollbar thumb'
        return body[0], body[-1]

    def at_top(strip):
        assert abs(thumb(strip)[0] - 18 * scale) <= 2, 'Thumb did not reach start of track'

    def at_bottom(strip):
        assert abs(strip.height - thumb(strip)[1] - 19 * scale) <= 2, 'Thumb did not reach end of track'

    def drag(strip, amount):
        mid = 3 + sum(thumb(strip)) / (2 * scale)
        pointer(245, mid)
        vmctl.button(VM, 'left', True)
        try:
            pointer(245, mid + amount / 2)
            pointer(245, mid + amount)
        finally:
            vmctl.button(VM, 'left', False)
        park()

    def wheel(direction):
        pointer(110, 180)
        for _ in range(18):
            vmctl.button(VM, f'wheel-{direction}', True)
            vmctl.button(VM, f'wheel-{direction}', False)
        park()

    open_group()
    start = rail('overflow-top')
    at_top(start)
    if scale == 1:
        native = Image.open(NATIVE).convert('RGB').crop((234, 2, 250, 380))
        native.save(out / 'native-rail.png')
        # Compare whole arrows, a full-width stipple block and thumb rims/middle; lengths and positions
        # depend on the different catalog sizes. Native thumb rows are 118 through 331 in this crop.
        first, last = thumb(start)
        for label, y, ref_y, h in [('up arrow', 0, 0, 16), ('down arrow', 362, 362, 16),
                                    ('track', 340, 340, 12), ('thumb top', first - 2, 118, 6),
                                    ('thumb bottom', last - 3, 326, 6)]:
            actual = start.crop((0, y, 16, y + h))
            expected = native.crop((0, ref_y, 16, ref_y + h))
            assert ImageChops.difference(actual, expected).getbbox() is None, f'{label} differs from native'
        print('Native arrow tiles, stipple and thumb rims match exactly', flush=True)
    else:
        assert start.width == 24 and abs(start.height - 567) <= 1, 'Overflow strip is not 16×378 logical pixels'

    click(245, 373)
    lower = rail('arrow-down')
    # A single click is one 18px row, not a page, and up reverses it.
    line = round(346 * scale * 18 / (OVERFLOW * 18))
    assert abs(thumb(lower)[0] - thumb(start)[0] - line) <= 2, 'Down arrow did not scroll one row'
    click(245, 11)
    at_top(rail('arrow-up'))
    click(245, 317)
    page = rail('page-down')
    travel = round(346 * scale * 376 / (OVERFLOW * 18))
    assert abs(thumb(page)[0] - thumb(start)[0] - travel) <= 2, 'Track did not page down one viewport'
    click(245, 35)
    at_top(rail('page-up'))
    print('Arrow and track movement verified in both directions', flush=True)

    drag(start, 215)
    bottom = rail('drag-bottom')
    at_bottom(bottom)
    drag(bottom, -215)
    at_top(rail('drag-top'))
    click(70, 14)
    expect_launch(base, 'AAA-01')
    open_group()
    drag(rail('drag-reopen'), 215)
    click(70, 372)
    expect_launch(base, f'AAA-{OVERFLOW:02}')

    open_group()
    wheel('down')
    at_bottom(rail('wheel-bottom'))
    click(70, 372)
    expect_launch(base, f'AAA-{OVERFLOW:02}')
    open_group()
    wheel('down')
    wheel('up')
    at_top(rail('wheel-top'))
    click(70, 14)
    expect_launch(base, 'AAA-01')

    for steps, endpoint, row_y, name in [(1, at_top, 14, 'AAA-01'),
                                         (OVERFLOW, at_bottom, 372, f'AAA-{OVERFLOW:02}')]:
        # Enter without hovering a leaf under the pointer, which would already select it.
        open_programs()
        key('DOWN')
        key('ENTER')
        for _ in range(steps):
            key('DOWN')
        endpoint(rail(f'keyboard-{steps}'))
        image = snap(out, f'keyboard-{steps}-selected')
        assert image.getpixel(pt(225, row_y)) == BLUE, 'Keyboard selection not visible in the endpoint row'
        key('ENTER')
        expect_launch(base, name)

    open_group()
    drag(rail('before-back'), 215)
    click(85, 407)  # Back from the child returns to the original app catalog.
    click(70, 14)
    at_top(rail('reentered'))
    print('Back and same-group re-entry reset the scroll position', flush=True)
    click(85, 407)
    click(70, 32)
    pointer(220, 14)
    fit = snap(out, 'fit-no-gutter')
    assert fit.getpixel(pt(247, 14)) == BLUE, 'Short list lost its full row width'
    assert fit.getpixel(pt(246, 370)) == (255, 255, 255), 'Short list shows a scrollbar'
    click(70, 14)
    expect_launch(base, 'AAB-01')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    parser.add_argument('--installed', action='store_true', help='test the installed Arch package')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    tool = executable('win7-classic', args.installed)
    assert user(f'{tool} status') == 'current', 'Run from the lab’s current mode'
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    set_scale = f'kscreen-doctor output.{output["name"]}.scale.'
    digest = ('for f in ~/.config/{kdeglobals,kwinrc,plasma-org.kde.plasma.desktop-appletsrc,plasmashellrc,plasmarc}; do '
              'if [[ -f $f ]]; then sha256sum "$f"; else echo "absent: $f"; fi; done')
    windows_digest = 'sha256sum ~/.local/state/win7-classic/profiles/windows/plasma-org.kde.plasma.desktop-appletsrc'
    with launchers() as (base, catalog):
        try:
            if output['scale'] != args.scale:
                user(f'{set_scale}{args.scale}')
                time.sleep(2)
            # Warm any existing layout migrations before measuring ordinary profile reuse.
            toggle('windows', packaged=args.installed)
            toggle('current', packaged=args.installed)
            current_before, windows_before, entries_before = user(digest), user(windows_digest), user(catalog)
            toggle('windows', packaged=args.installed)
            try:
                exercise(args.out, args.scale, base)
            finally:
                key('ESC')
                toggle('current', packaged=args.installed)
            assert user(digest) == current_before, 'Current-mode appearance or panel bytes changed'
            assert user(windows_digest) == windows_before, 'Using the scrollbar changed the saved Windows layout'
            assert user(catalog) == entries_before, 'App catalog fixtures changed'
            assert 'plugin=org.kde.plasma.kickoff' in user('cat ~/.config/plasma-org.kde.plasma.desktop-appletsrc')
            key('LEFTMETA')
            time.sleep(.5)
            vmctl.type_text(VM, 'W7 Scroll QA AAB 20')
            snap(args.out, 'current-stock-search')
            key('ENTER')
            expect_launch(base, 'AAB-20')
        finally:
            if output['scale'] != args.scale:
                user(f'{set_scale}{output["scale"]}')
    print(f'PASS: All Programs scrollbar at {args.scale:g}x; current and Windows layouts, and app catalog preserved')


if __name__ == '__main__':
    main()
