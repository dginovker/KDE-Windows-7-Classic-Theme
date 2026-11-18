#!/usr/bin/env python3
"""Drive the production All Programs at 100% and 150% (#43)."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, install, shot, toggle, user, vmctl, wait_for

REF = ROOT / 'reference/screenshots/w7-programs.png'
BLUE = (10, 36, 106)


@contextmanager
def nested_program():
    # Use the real XDG menu cache: an ordinary lab install need not have any populated subgroups.
    stem = Path(user('mktemp -d /tmp/w7-program-group.XXXXXXXX')).name
    base = Path('/tmp') / stem
    paths = [f'~/.config/menus/applications-merged/{stem}.menu',
             f'~/.local/share/desktop-directories/{stem}.directory',
             f'~/.local/share/applications/{stem}.desktop']
    user('test ! -e ' + ' && test ! -e '.join(paths))
    try:
        user(f'''set -euC
mkdir -p ~/.config/menus/applications-merged ~/.local/share/{{desktop-directories,applications}}
cat > {paths[0]} <<'EOF'
<Menu><Name>Applications</Name><Menu><Name>AAA Classic QA</Name><Menu><Name>Nested</Name>
<Directory>{stem}.directory</Directory><Include><Filename>{stem}.desktop</Filename></Include>
</Menu></Menu></Menu>
EOF
cat > {paths[1]} <<'EOF'
[Desktop Entry]
Type=Directory
Name=Nested
Icon=applications-development
EOF
cat > {paths[2]} <<'EOF'
[Desktop Entry]
Type=Application
Name=Classic QA Terminal Fixture
Icon=utilities-terminal
Exec=/usr/bin/touch {base}/launched
EOF
kbuildsycoca6''')
        yield base / 'launched'
    finally:
        user(f'rm -f {" ".join(paths)} {base}/launched; rmdir {base}; kbuildsycoca6')


def exercise(out, scale, marker):
    native = Image.open(REF).convert('RGB').crop((6, 479, 22, 495))
    art = Image.open(ROOT / 'explorer/assets' / ('folder-16.png' if scale == 1 else 'folder-32.png')).convert('RGBA')
    errors = []
    top = 800 - round(505 * scale)

    def snap(name):
        time.sleep(.4)
        path = out / f'{name}.png'
        shot(path)
        with Image.open(path) as image:
            assert image.size == (1280, 800), image.size
            return image.convert('RGB')

    def click(x, y):
        vmctl.pointer(VM, round(x * scale), top + round(y * scale), 'left')
        vmctl.pointer(VM, 640, 790)
        time.sleep(.3)

    def key(*codes):
        for code in codes:
            vmctl.keys(VM, 'KEY_' + code)

    def icon(image, row=0):
        size = round(16 * scale)
        x, y = round(7 * scale), top + round((6 + 18 * row) * scale)
        return image.crop((x, y, x + size, y + size))

    def colored(image):
        # Count pixels of the gold folder, not the blue highlight, white field or monochrome icon.
        return sum(1 for r, g, b in image.get_flattened_data() if r > 150 and g > 120 and g > b + 24)

    def check_folder(image, name, row=0, selected=False):
        actual = icon(image, row)
        expected = Image.new('RGBA', actual.size, BLUE if selected else 'white')
        expected.alpha_composite(art.resize(actual.size, Image.Resampling.BILINEAR))
        expected = expected.convert('RGB')
        if scale == 1:
            if not selected:
                assert not ImageChops.difference(expected, native).getbbox(), 'Asset no longer matches genuine Accessories'
            delta = ImageChops.difference(actual, expected)
            difference = sum(1 for rgb in delta.get_flattened_data() if max(rgb) > 1)
            if difference:
                errors.append(f'{name}: {difference}/256 pixels differ from the native icon')
        else:
            count, want = colored(actual), colored(expected)
            if not .85 * want <= count <= 1.15 * want:
                errors.append(f'{name}: {count} gold pixels at 150%, expected about {want}')

    def open_programs():
        key('LEFTMETA')
        time.sleep(.5)
        click(85, 407)

    def launch():
        wait_for(lambda: user(f'test ! -f {marker} || echo launched') == 'launched', 'fixture launch')
        user(f'rm {marker}')

    open_programs()
    root = snap('programs')
    check_folder(root, 'stock Development', row=1)
    key('DOWN', 'ENTER')
    check_folder(snap('keyboard-expanded'), 'nested group')
    key('DOWN')
    check_folder(snap('keyboard-selected'), 'selected nested group', selected=True)
    key('ENTER')
    leaf = snap('keyboard-nested')
    assert colored(icon(leaf)) == 0 and icon(leaf).getcolors() != [(icon(leaf).width ** 2, (255, 255, 255))], 'app icon lost'
    key('DOWN', 'ENTER')
    launch()

    open_programs()
    click(70, 14)
    click(70, 14)
    mouse_icon = icon(snap('mouse-nested'))
    assert colored(mouse_icon) == 0 and len(mouse_icon.getcolors()) > 2, 'mouse expansion did not show the app icon'
    click(85, 407)
    check_folder(snap('back-to-parent'), 'parent after Back')
    click(85, 407)
    check_folder(snap('back-to-programs'), 'Development after Back', row=1)
    click(85, 407)
    assert snap('back-to-favorites').getpixel((200, top + round(170 * scale))) == (212, 208, 200)
    click(85, 407)
    click(70, 14)
    click(70, 14)
    vmctl.pointer(VM, round(70 * scale), top + round(14 * scale), 'left')
    vmctl.pointer(VM, 640, 790)
    launch()

    open_programs()
    vmctl.type_text(VM, 'Classic QA Terminal Fixture')
    snap('search-from-programs')
    key('ENTER')
    launch()
    print(f'{scale:g}x: mouse and keyboard nested expansion, Back, leaf launch and search launch pass', flush=True)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install(reset=False)
    status = user('~/.local/bin/win7-classic status')
    assert status == 'current', 'Run from the lab’s current mode'
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    scale_setting = f'kscreen-doctor output.{output["name"]}.scale.'
    digest = 'sha256sum ~/.config/{kdeglobals,kwinrc,plasma-org.kde.plasma.desktop-appletsrc}'
    with nested_program() as marker:
        try:
            if output['scale'] != args.scale:
                user(f'{scale_setting}{args.scale}')
                # Let Plasma persist its resized current panel before measuring a theme round trip.
                time.sleep(2)
            before = user(digest)
            toggle('windows')
            try:
                errors = exercise(args.out, args.scale, marker)
            finally:
                vmctl.keys(VM, 'KEY_ESC')
                toggle(status)
            after = user(digest)
            assert before == after, f'Current KDE files changed:\n{before}\n→\n{after}'
        finally:
            if output['scale'] != args.scale:
                user(f'{scale_setting}{output["scale"]}')
    print('Current KDE files restored byte-for-byte', flush=True)
    assert not errors, '\n'.join(errors)
    print(f'PASS: genuine All Programs group artwork at {args.scale:g}x')


if __name__ == '__main__':
    main()
