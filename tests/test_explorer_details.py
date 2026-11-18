#!/usr/bin/env python3
"""Compare production Explorer Details with the genuine 96-DPI listing (issue #36)."""
import argparse
from pathlib import Path
import re
import shlex
import subprocess
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, install, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, GEOMETRY, VIEW_MENU, captions, click, key

NATIVE = ROOT / 'reference/screenshots/w7-explorer-details.png'
WHITE = (255, 255, 255)
FOLDERS = 'Documents Downloads Music Pictures Projects'.split()
HEADERS = ('Name', 'Date modified', 'Type', 'Size')
DIVIDERS = (692, 812, 932, 1012)  # first pixel of each following section
LISTING = (420, 210, 1020, 365)


def read_text(image, out, tag, box, psm=7):
    part = image.crop(box)
    path = out / f'{tag}.png'
    part.resize((part.width * 4, part.height * 4), Image.Resampling.LANCZOS).save(path)
    text = subprocess.check_output(['tesseract', str(path), 'stdout', '--psm', str(psm)], text=True).strip()
    (out / f'{tag}.txt').write_text(text + '\n')
    return text


def text_bands(image, box):
    x, y, right, bottom = box
    image = image.convert('L')
    bands = []
    for row in range(y, bottom):
        if image.crop((x, row, right, row + 1)).getextrema()[0] < 140:
            if bands and row == bands[-1][1]:
                bands[-1][1] = row + 1
            else:
                bands.append([row, row + 1])
    return bands


def check_listing(out, actual, native):
    # No resizing or translated panel coordinates: both screen captures are 1280x800 at 100%.
    for tag, image in [('native', native), ('actual', actual)]:
        image.crop(LISTING).save(out / f'{tag}-listing.png')
    ImageChops.difference(actual.crop(LISTING), native.crop(LISTING)).save(out / 'listing-diff.png')
    assert actual.size == native.size == (1280, 800), (actual.size, native.size)
    headers = tuple(read_text(actual, out, f'heading-{i}', box)
                    for i, box in enumerate(((430, 213, 466, 230), (694, 213, 806, 230),
                                             (814, 213, 926, 230), (934, 213, 1006, 230))))
    columns = [x for x in DIVIDERS if all(min(actual.getpixel((x - 1, y))) < 145 for y in range(213, 216))]
    white = actual.crop((562, 243, 625, 345)).getcolors() == [(63 * 102, WHITE)]
    sizes_blank = actual.crop((940, 239, 1009, 348)).getextrema() == ((255, 255),) * 3
    bands = text_bands(actual, (456, 234, 531, 350))
    expected_bands = text_bands(native, (456, 234, 531, 350))
    names = read_text(actual, out, 'folders', (454, 234, 540, 355), 6).split()
    dates = read_text(actual, out, 'timestamps', (694, 234, 808, 355), 6).splitlines()
    expected_dates = ['11/14/2026 7:39 AM'] * len(FOLDERS)
    print(f'headers={headers} dividers={columns}, white={white}, empty folder sizes={sizes_blank}; '
          f'names={names}, dates={dates}, text bands={bands} (native {expected_bands})', flush=True)
    assert headers == HEADERS, headers
    assert columns == list(DIVIDERS), columns
    assert white and sizes_blank and names == FOLDERS and dates == expected_dates
    assert len(bands) == len(expected_bands) == len(FOLDERS), bands
    assert all(abs(a[0] - b[0]) <= 5 for a, b in zip(bands, expected_bands)), bands
    assert all(abs(p[0] - q[0] - 22) <= 2 for p, q in zip(bands[1:], bands)), bands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true', help='use the Explorer already installed in Windows mode')
    parser.add_argument('--native', type=Path, default=NATIVE)
    parser.add_argument('--explorer', default='/home/tester/.local/bin/win7-explorer',
                        help='lab executable for a baseline run; use an absolute guest path')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    if not args.installed:
        install()
        toggle('windows')
    root = user('mktemp -d /tmp/w7-details.XXXXXXXX')
    unit = Path(root).name
    folder = f'{root}/Classic-demo'
    user(f'''mkdir -p {folder}/{{{','.join(FOLDERS)}}} {root}/more {root}/config
cp "$HOME/.config/kdeglobals" {root}/config/
# Set local wall times as text, then let the filesystem and KIO carry actual timestamps.
touch -t 202611140739 {folder}/*
printf a > {root}/more/Beta.txt
head -c 10240 /dev/zero > {root}/more/Alpha.txt
touch -t 202511140901 {root}/more/Alpha.txt
touch -t 202402010739 {root}/more/Beta.txt
for n in $(seq -w 36); do mkdir {root}/more/Row$n; done''')

    def snapshot(tag):
        vmctl.pointer(VM, 1150, 700)
        time.sleep(.35)
        path = args.out / f'{tag}.png'
        shot(path)
        return Image.open(path).convert('RGB')

    def details():
        click(VIEW_MENU)
        key('KEY_UP')
        key('KEY_ENTER')

    def names(tag, box=(453, 233, 556, 620)):
        image = snapshot(tag)
        return read_text(image, args.out, f'{tag}-names', box, 6)

    def folder_digest():
        return user(f'find {root}/Classic-demo {root}/more -printf "%p %T@ %s\\n" | sort; '
                    f'find {root}/more -type f -exec sha256sum {{}} + | sort')

    before = folder_digest()
    try:
        executable = shlex.quote(args.explorer)
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={root}/config '
             f'--setenv=LC_ALL=en_US.UTF-8 {executable} {folder}')
        wait_for(lambda: 'Classic-demo' in captions(), 'production Explorer at Classic-demo')
        kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" '
                    f'&& w.caption == "Classic-demo") {{ w.frameGeometry = {GEOMETRY}; workspace.activeWindow = w; }}')
        details()
        check_listing(args.out, snapshot('ordinary'), Image.open(args.native).convert('RGB'))
        click((480, 247))
        selected = snapshot('mouse-selection')
        assert (10, 36, 106) in selected.crop((430, 234, 548, 259)).getdata(), 'no focused selection'
        key('KEY_DOWN')
        key('KEY_ENTER')
        wait_for(lambda: 'Downloads' in captions(), 'Down selects Downloads and Enter opens it')
        key('KEY_LEFTALT', 'KEY_LEFT')
        assert 'Projects' in names('back-to-details'), 'Back did not restore Details'
        key('KEY_LEFTALT', 'KEY_D')
        vmctl.type_text(VM, f'{root}/more\n')
        wait_for(lambda: 'more' in captions(), 'navigation to scroll fixture')
        details()
        click((480, 246))
        key('KEY_END')
        # Use real mouse scrolling (not a data/model API); the list is still taller than the viewport.
        vmctl.pointer(VM, 610, 420)
        vmctl.button(VM, 'wheel-up', True)
        vmctl.button(VM, 'wheel-up', False)
        scrolled = names('wheel-up')
        assert 'Row01' not in scrolled and 'Beta.txt' not in scrolled and re.search(r'Row[1-3][0-9]', scrolled), scrolled
        key('KEY_END')
        tail = snapshot('end')
        tail_names = read_text(tail, args.out, 'end-names', (453, 233, 556, 620), 6)
        assert 0 <= tail_names.find('Alpha.txt') < tail_names.find('Beta.txt'), tail_names
        assert any(min(pixel) < 140 for pixel in tail.crop((946, 550, 1008, 620)).get_flattened_data()), 'file Size cells are blank'
        click((959, 220))
        key('KEY_END')
        small_first = names('size-ascending-end')
        assert 0 <= small_first.find('Beta.txt') < small_first.find('Alpha.txt'), small_first
        click((734, 220))
        key('KEY_END')
        old_first = names('date-ascending-end')
        assert 0 <= old_first.find('Beta.txt') < old_first.find('Alpha.txt'), old_first
        click((734, 220))
        key('KEY_END')
        new_first = names('date-descending-end')
        assert 0 <= new_first.find('Alpha.txt') < new_first.find('Beta.txt'), new_first
        assert folder_digest() == before, 'Details wrote fixture data or mtimes'
        key('KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: 'more' not in captions(), 'Ctrl+W closes the Details window')
        print('PASS: native Details listing, actual mouse selection and wheel, keyboard and numeric/date header sorts')
    finally:
        user(f'systemctl --user stop {unit} || true; rm -r {root}')
        if not args.installed:
            toggle('current')


if __name__ == '__main__':
    main()
