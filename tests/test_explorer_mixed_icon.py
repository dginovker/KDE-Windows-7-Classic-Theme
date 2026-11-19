#!/usr/bin/env python3
"""Exercise the real mixed Details glyph and Open at both display scales."""
import argparse
import json
from pathlib import Path
import time

from PIL import Image, ImageChops

from lab import VM, clipboard, executable, explorer_identity, install, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, click, key
from test_explorer_command_menus import words
from test_explorer_empty import stop_unit
from test_explorer_selection import KATE, activate, app_windows, unit_pid


def run(out, base, target, scale, explorer):
    folder = f'{base}/Mixed'
    unit = Path(base).name
    assert not app_windows(), 'requires an unused Explorer and Kate session'
    slots = {}
    x, y, w, h = place = (256, 120, 768, 560) if scale == 1 else (40, 40, 768, 440)

    def pt(a, b):
        return round((x + a) * scale), round((y + b) * scale)

    def take(name):
        vmctl.pointer(VM, 1240, 700)
        time.sleep(.5)
        path = out / f'{name}.png'
        shot(path)
        with Image.open(path) as im:
            assert im.size == (1280, 800), im.size
            return im.convert('RGB')

    def strip(name):
        im = take(name)
        sx, sy = pt(21, h - 52)
        # KWin rounds the bottom frame separately at 150%.
        if scale == 1.5:
            sy += 1
        icon = im.crop((sx, sy, sx + round(48 * scale), sy + round(46 * scale)))
        icon.save(out / f'{name}-slot.png')
        slots[name] = icon
        area = (*pt(81, h - 52), *pt(w - 14, h - 6))
        im.crop(area).save(out / f'{name}-metadata.png')
        text = ' '.join(words(im, area).split())
        print(f'{name}: {text}', flush=True)
        return text

    def check(name, *expected):
        text = strip(name)
        assert all(word in text for word in expected), (name, expected, text)

    def add(direction):
        key('KEY_LEFTCTRL', direction)
        key('KEY_LEFTCTRL', 'KEY_SPACE')

    try:
        user(f'''set -eu
mkdir -p {folder}/AFolder {base}/config {base}/kate
cp ~/.config/kdeglobals {base}/config/; cp ~/.config/kdeglobals {base}/kate/
cat > {base}/config/mimeapps.list <<'EOF'
[Default Applications]
text/plain=org.kde.kate.desktop;
inode/directory=org.win7classic.explorer.desktop;
EOF
printf 'mixed details proof\\n' > {folder}/Sample.txt
TZ=UTC touch -t 201001020304 {folder}/AFolder
TZ=UTC touch -t 201203040506 {folder}/Sample.txt
systemd-run --user --collect -q --unit={unit} --setenv=TZ=UTC --setenv=LC_ALL=en_US.UTF-8 \\
    --setenv=XDG_CONFIG_HOME={base}/config {explorer} {folder}
''')
        pid = unit_pid(unit)
        wait_for(lambda: (pid, EXPLORER, 'Mixed') in app_windows(), 'packaged mixed fixture')
        explorer_identity(pid, explorer, out)
        activate(pid, place)
        wait_for(lambda: strip('unselected') == '2 items', 'KIO listed the two fixture items')
        folder_point, file_point, blank = pt(221, 150), pt(338, 150), pt(614, 300)
        click(folder_point)
        check('folder', 'AFolder', 'File folder', 'Date modified', '1/2/2010')
        add('KEY_RIGHT')
        check('folder-first', '2 items selected', 'Date modified', '1/2/2010', '3/4/2012')
        add('KEY_LEFT')
        check('file-restored', 'Sample.txt', 'Date modified', '3/4/2012', 'Size:')
        click(blank)
        text = strip('cleared-after-file')
        assert text == '2 items', text
        click(file_point)
        check('file', 'Sample.txt', 'Date modified', '3/4/2012', 'Size:')
        add('KEY_LEFT')
        check('file-first', '2 items selected', 'Date modified', '1/2/2010', '3/4/2012')
        add('KEY_RIGHT')
        check('folder-restored', 'AFolder', 'File folder', 'Date modified', '1/2/2010')
        click(blank)
        text = strip('cleared-after-folder')
        assert text == '2 items', text
        assert slots['file'] != slots['folder']
        for restored, expected in (('file-restored', 'file'), ('folder-restored', 'folder'),
                                   ('cleared-after-file', 'unselected'), ('cleared-after-folder', 'unselected')):
            assert slots[restored] == slots[expected], (restored, expected)

        user(f'printf "unrelated tab\\n" > {base}/Control.txt; systemd-run --user --collect -q '
             f'--unit={unit}-kate --setenv=XDG_CONFIG_HOME={base}/kate kate --new --startanon {base}/Control.txt')
        kate = unit_pid(unit + '-kate')
        wait_for(lambda: any(p == kate and cls == KATE and c.startswith('Control.txt')
                             for p, cls, c in app_windows()), 'real Kate control tab')
        activate(pid, place)
        click(file_point)
        add('KEY_LEFT')
        check('before-open', '2 items selected', 'Date modified')
        click(pt(122, 74))  # The painted Open command, not the default click on a file.
        wait_for(lambda: any(p == kate and cls == KATE and c.startswith('Sample.txt')
                             for p, cls, c in app_windows()), 'Open delivered the selected file to Kate')
        wait_for(lambda: any(p != pid and cls == EXPLORER and c == 'AFolder'
                             for p, cls, c in app_windows()), 'Open created a separate Explorer folder window')
        child, = (p for p, cls, c in app_windows() if cls == EXPLORER and c == 'AFolder')
        path = user(f'''tr '\\0' '\\n' </proc/{child}/cmdline | grep -Fx -e {folder}/AFolder -e file://{folder}/AFolder''')
        (out / 'open-targets.txt').write_text(path + '\n')
        activate(child)
        take('open-folder')
        activate(kate)
        take('open-file')
        user('wl-copy --clear')
        key('KEY_LEFTCTRL', 'KEY_A')
        key('KEY_LEFTCTRL', 'KEY_C')
        copied = clipboard()
        assert copied == 'mixed details proof', copied
        with (out / 'open-targets.txt').open('a') as log:
            log.write(copied + '\n')
        activate(pid, place)
        check('after-open', '2 items selected', 'Date modified', '1/2/2010', '3/4/2012')
        assert slots['before-open'] == slots['after-open']

        if scale == 1.5:
            # Qt raster sampling at this half-pixel origin resolves ties toward the source origin.
            scaled = Image.new('RGB', (72, 69))
            scaled.putdata([target.getpixel((x * 2 // 3, y * 2 // 3))
                            for y in range(scaled.height) for x in range(scaled.width)])
            target = scaled
        target.save(out / 'native-slot.png')
        failures = []
        for name in ('folder-first', 'file-first', 'before-open', 'after-open'):
            diff = ImageChops.difference(slots[name], target)
            pixels = sum(rgb != (0, 0, 0) for rgb in diff.get_flattened_data())
            print(f'{name}: {pixels} non-native pixels in {target.width}x{target.height}', flush=True)
            if pixels:
                failures.append(name)
        assert not failures, f'non-native Details glyph: {failures}'
        assert all(slots[name] != target for name in ('file', 'folder', 'unselected'))
        print('PASS mixed slot, single/clear restoration, metadata and real mixed Open', flush=True)
    finally:
        stop_unit(unit)
        stop_unit(unit + '-kate')
        for p, cls, caption in app_windows():
            if cls == EXPLORER and caption == 'AFolder' and user(
                    rf'''tr '\0' '\n' </proc/{p}/cmdline | grep -Fx -e {folder}/AFolder -e file://{folder}/AFolder''', check=False):
                activate(p)
                key('KEY_LEFTALT', 'KEY_F4')
                wait_for(lambda: all(row[0] != p for row in app_windows()), 'Open child closed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('native_mixed', type=Path,
                        help='96-DPI full screen with the mixed glyph at (275,628)')
    installed = parser.add_mutually_exclusive_group()
    installed.add_argument('--installed', action='store_true')
    installed.add_argument('--packaged', action='store_true')
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    args = parser.parse_args()
    try:
        with Image.open(args.native_mixed) as native:
            native.verify()
        with Image.open(args.native_mixed) as native:
            if native.size != (1280, 800):
                parser.error(f'{args.native_mixed}: expected 1280x800, got {native.size}')
            target = native.convert('RGB').crop((275, 628, 323, 674))
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        parser.error(f'{args.native_mixed}: {exc}')
    args.out.mkdir(parents=True, exist_ok=True)
    if not (args.installed or args.packaged):
        install(reset=False)
    explorer = executable('win7-explorer', args.packaged)
    tool = executable('win7-classic', args.packaged)
    mode = user(f'{tool} status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    base = user('mktemp -d /tmp/w7-mixed.XXXXXX')
    try:
        user(f'kscreen-doctor output.{output["name"]}.scale.{args.scale}')
        toggle('windows', packaged=args.packaged)
        run(args.out, base, target, args.scale, explorer)
    finally:
        user(f'rm -r {base}; kscreen-doctor output.{output["name"]}.scale.{output["scale"]}')
        toggle(mode, packaged=args.packaged)


if __name__ == '__main__':
    main()
