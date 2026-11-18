#!/usr/bin/env python3
"""Drive per-folder Explorer preferences through real menus, headers and navigation in the lab."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
import shlex
import time
import subprocess

from PIL import Image

from lab import VM, install, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, GEOMETRY, captions, click, key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    if not args.installed:
        install()
        toggle('windows')
    root = user('mktemp -d /tmp/w7-preferences.XXXXXXXX')
    config = f'{root}/config/win7-explorer-viewsrc'
    user(f'''mkdir {root}/{{config,Alpha,Beta,Gamma,Malformed}}
for dir in Alpha Beta Malformed; do
    printf 'larger\n' > {root}/$dir/Able.txt
    printf 'z' > {root}/$dir/Zulu.txt
    touch -t 202001010000 {root}/$dir/Able.txt
    touch -t 202201010000 {root}/$dir/Zulu.txt
done''')
    units = []

    def state():
        return user(f'''python - {root} <<'PY'
from hashlib import sha256
from pathlib import Path
import os, sys
root = Path(sys.argv[1]); home = Path.home()
for base in [root/'Alpha', root/'Beta', root/'Gamma', root/'Malformed', root/'config',
             home/'.config/dolphinrc', home/'.local/share/dolphin', home/'.config/kdeglobals']:
    for p in [base, *sorted(base.rglob('*'))]:
        if p.exists() and p != root/'config/win7-explorer-viewsrc':
            print(p, {{key:os.getxattr(p, key).hex() for key in sorted(os.listxattr(p))}},
                  sha256(p.read_bytes()).hexdigest() if p.is_file() else 'dir')
PY''')

    def digest():
        return user(f'if test -e {config}; then stat -c "%i %y" {config}; sha256sum {config}; fi')

    def launch(folder, url=None):
        unit = f'{Path(root).name}-{len(units)}'
        units.append(unit)
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={root}/config '
             f'~/.local/bin/win7-explorer {shlex.quote(url or f"{root}/{folder}")}')
        wait_for(lambda: folder in captions(), f'window on {folder}')
        kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" '
                    f'&& w.caption == "{folder}") {{ w.frameGeometry = {GEOMETRY}; workspace.activeWindow = w; }}')

    def go(folder, url=None):
        key('KEY_LEFTALT', 'KEY_D')
        vmctl.type_text(VM, (url or f'{root}/{folder}/') + '\n')
        wait_for(lambda: folder in captions(), f'navigation to {folder}')
        vmctl.pointer(VM, 640, 700)

    def rows(name, first, last, date_order=None):
        path = args.out / f'{name}.png'
        vmctl.pointer(VM, 640, 700)
        shot(path)
        crop = path.with_name(f'{name}-rows.png')
        with Image.open(path) as image:
            image.crop((422, 209, 565, 299)).resize((572, 360)).save(crop)
            if date_order:
                # The native triangle follows the label rather than hugging the right divider.
                match = [x for x in range(755, 799) if all(
                    image.getpixel((x + offset, y)) == (128, 128, 128)
                    for y, length in zip(range(219, 222), (1, 3, 5) if date_order == 'ascending' else (5, 3, 1))
                    for offset in range((5 - length) // 2, (5 + length) // 2))]
                assert match, f'{name}: no {date_order} arrow in Date column'
        text = subprocess.check_output(['tesseract', str(crop), 'stdout', '--psm', '6'], text=True)
        assert 'Name' in text and 0 <= text.find(first) < text.find(last), f'{name}: {text!r}'

    def large_icons(name):
        path = args.out / f'{name}.png'
        shot(path)
        with Image.open(path) as image:
            assert image.convert('RGB').getpixel((650, 218)) == (255, 255, 255), f'{name}: Details header remained'

    def view_menu():
        click((942, 194))
        key('KEY_UP')
        key('KEY_ENTER')

    def checked_menu(name, expected, view=False, negative_control=False):
        if view:
            click((942, 194))
        else:
            click((850, 420), 'right')
            key('KEY_B')
        frame = args.out / f'{name}.png'
        time.sleep(.4)
        shot(frame)
        key('KEY_ESC')
        if not view:
            key('KEY_ESC')
        with Image.open(frame) as image:
            menu = image.convert('RGB')
        # Keep View's decorative icons out of OCR so each candidate is the full label, not a suffix.
        origin = 960 if view else 850
        labels = menu.crop((origin, 200, 1280, 700))
        ocr = args.out / f'{name}-ocr.png'
        labels.resize((labels.width * 3, labels.height * 3)).save(ocr)
        tsv = subprocess.check_output(['tesseract', str(ocr), 'stdout', '--psm', '11', 'tsv'], text=True)
        lines = {}
        for word in csv.DictReader(tsv.splitlines(), delimiter='\t'):
            if word['text'].strip():
                key_id = (word['block_num'], word['par_num'], word['line_num'])
                lines.setdefault(key_id, []).append(word)
        markers = {}
        for words in lines.values():
            text = ' '.join(word['text'] for word in words)
            if text not in expected:
                continue
            word = words[0]
            x = origin + int(word['left']) // 3 - (39 if view else 21)
            y = 199 + (int(word['top']) + int(word['height']) // 2) // 3
            markers[text] = (x - 3, y - 3, x + 3, y + 3)
        assert set(markers) == set(expected), (name, markers, tsv)

        def checked(image, label):
            # Only sample the small centre of the Breeze radio, not its outline or the text.
            return sum(pixel < 65 for pixel in image.crop(markers[label]).convert('L').get_flattened_data()) >= 6

        assert all(checked(menu, label) for label in expected), (name, markers)
        if negative_control:
            dot = markers['Sort by Date']
            unchecked = (dot[0], dot[1] - 29, dot[2], dot[3] - 29)
            negative = menu.copy()
            negative.paste(menu.crop(unchecked), dot)
            negative.save(args.out / f'{name}-negative-no-date-dot.png')
            assert not checked(negative, 'Sort by Date') and checked(negative, 'Oldest First'), markers
            print('Date radio detector rejects the dot-removed copy; untouched capture passes')

    def focus(unit):
        pid = user(f'systemctl --user show -p MainPID --value {unit}')
        assert int(pid) > 1
        kwin_script(f'for (const w of workspace.windowList()) if (w.pid == {pid}) workspace.activeWindow = w;')

    start = state()
    try:
        launch('Gamma')
        go('Alpha')
        assert not digest(), 'navigation created a preferences file'
        view_menu()
        rows('alpha-default', 'Able', 'Zulu')
        click((480, 218))
        rows('alpha-name-desc', 'Zulu', 'Able')
        before = digest()
        go('Beta')
        large_icons('beta-default')
        assert digest() == before, 'visiting an unseen folder wrote preferences'
        click((875, 420), 'right')
        key('KEY_B')
        for _ in range(3):
            key('KEY_DOWN')
        key('KEY_ENTER')
        before = digest()
        key('KEY_LEFTALT', 'KEY_LEFT')
        rows('alpha-back', 'Zulu', 'Able')
        key('KEY_LEFTALT', 'KEY_RIGHT')
        large_icons('beta-forward')
        shot(args.out / 'beta-sort.png')
        # Zulu is visibly in the first icon cell and Able in the second.
        with Image.open(args.out / 'beta-sort.png') as image:
            crop = args.out / 'beta-sort-labels.png'
            image.crop((428, 298, 660, 340)).resize((928, 168)).save(crop)
        text = subprocess.check_output(['tesseract', str(crop), 'stdout', '--psm', '6'], text=True)
        assert 0 <= text.find('Zulu') < text.find('Able'), repr(text)
        launch('Alpha', f'file://{root}/Beta/../%41lpha/?fixture=1#test')
        rows('alpha-new-window', 'Zulu', 'Able')
        key('KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: 'Alpha' not in captions(), 'fresh window closed')
        kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" && w.caption == "Beta") workspace.activeWindow = w;')
        key('KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: 'Beta' not in captions(), 'original window closed')
        for unit in units:
            assert user(f'systemctl --user show -p MainPID --value {unit}', check=False) == '0', unit
        launch('Alpha')
        rows('alpha-restarted', 'Zulu', 'Able')
        assert before and digest() == before, 'read-only restores changed the store, or no preferences saved'
        click((735, 224))
        rows('alpha-oldest-first', 'Able', 'Zulu', 'ascending')
        go('Gamma')
        key('KEY_LEFTALT', 'KEY_LEFT')
        rows('alpha-restored-oldest-first', 'Able', 'Zulu', 'ascending')
        checked_menu('alpha-restored-view', ['Details'], view=True)
        checked_menu('alpha-restored-oldest-menu', ['Sort by Date', 'Oldest First'], negative_control=True)
        click((735, 224))
        rows('alpha-newest-first', 'Zulu', 'Able', 'descending')
        saved = digest()
        go('Gamma')
        go('Alpha', f'file://{root}/Alpha#different')
        rows('alpha-restored-newest-first', 'Zulu', 'Able', 'descending')
        checked_menu('alpha-restored-newest-menu', ['Sort by Date', 'Newest First'])
        assert digest() == saved and state() == start

        # Both processes read the old view/sort. One changes only the view and the other only sort.
        writer_a = units[-1]
        launch('Beta')
        writer_b = units[-1]
        go('Alpha')
        focus(writer_a)
        click((917, 194))  # cycle Details to Extra Large Icons
        focus(writer_b)
        click((735, 224))  # oldest-first, while still in Details in the second process
        go('Gamma')
        go('Alpha')
        large_icons('alpha-merged-view')
        view_menu()  # list order reveals the independently saved sort
        rows('alpha-merged-sort', 'Able', 'Zulu', 'ascending')

        # A corrupt field is not interpreted as zero (Extra Large Icons / missing sort flags).
        bad_key = sha256(f'file://{root}/Malformed'.encode()).hexdigest()
        user(f'printf "\\n[{bad_key}]\\nView=broken\\nSort=9999\\n" >> {config}')
        saved = digest()
        go('Malformed')
        large_icons('malformed-normal-view')
        assert digest() == saved and state() == start
        view_menu()
        rows('malformed-default-sort', 'Able', 'Zulu')
        assert state() == start, 'folder contents/xattrs or Dolphin/shared preferences changed'
        print('PASS: per-folder view and real order, menu/header, back/forward, fresh window, restart; no read-only writes')
    finally:
        user('systemctl --user stop ' + ' '.join(units) + ' || true')
        user(f'rm -r {root}')


if __name__ == '__main__':
    main()
