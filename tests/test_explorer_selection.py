#!/usr/bin/env python3
"""Drive the production Explorer selection pane and Open command (issue #37)."""
import argparse
import json
from pathlib import Path
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, install, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, key
from test_explorer_details import read_text, text_bands

NATIVE = ROOT / 'reference/screenshots/w7-explorer-selection.png'
KATE = 'org.kde.kate'


def exercise(out, scale, root):
    out.mkdir(parents=True)
    folder = f'{root}/Classic-demo'
    unit = f'{Path(root).name}-{round(scale * 100)}'
    x, y, width, height = (256, 120, 768, 560) if scale == 1 else (40, 40, 768, 440)

    def point(dx, dy):
        return round((x + dx) * scale), round((y + dy) * scale)

    def region(x0, y0, x1, y1):
        return (*point(x0, y0), *point(x1, y1))

    def snap(tag):
        vmctl.pointer(VM, 1250, 705)
        time.sleep(.5)
        path = out / f'{tag}.png'
        shot(path)
        image = Image.open(path).convert('RGB')
        assert image.size == (1280, 800), image.size
        return image

    def check(tag, top, bottom, *, selected=True, oracle=None):
        image = snap(tag)
        rows = [region(77, height - 51 + dy, width - 10, height - 51 + dy + 16)
                for dy in (4, 22)]
        for i, (box, pieces) in enumerate(zip(rows, (top, bottom))):
            if not pieces:
                assert text_bands(image, box) == [], f'{tag}: stale metadata on row {i}'
                continue
            actual = read_text(image, out, f'{tag}-row{i}', box)
            print(f'{scale:g}x {tag} row {i}: {actual}', flush=True)
            compact = lambda s: ''.join(s.lower().split())
            assert all(compact(s) in compact(actual) for s in pieces), (tag, pieces, actual)
            if oracle is not None:
                with Image.open(NATIVE) as native:
                    target = text_bands(native, (77, oracle * 88 + 41 + i * 18, 756, oracle * 88 + 57 + i * 18))
                actual_bands = text_bands(image, box)
                assert target and actual_bands
                actual_start = (actual_bands[0][0] - box[1]) / scale
                assert abs(actual_start - (target[0][0] - (oracle * 88 + 41 + i * 18))) <= 2, (tag, actual_bands, target)
        open_box = region(108, 64, 140, 82)
        if selected:
            actual = read_text(image, out, f'{tag}-open', open_box)
            assert actual == 'Open', (tag, actual)
        else:
            return image.crop(region(4, 58, 410, 90))

    def focus_root():
        kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" '
                    f'&& w.caption == "Classic-demo") {{ w.frameGeometry = {{x:{x}, y:{y}, width:{width}, height:{height}}}; '
                    'workspace.activeWindow = w; }')

    try:
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=LC_ALL=en_US.UTF-8 '
             f'~/.local/bin/win7-explorer {folder}')
        wait_for(lambda: 'Classic-demo' in captions(), 'selection fixture Explorer')
        focus_root()
        bare = check('none', ('7 items',), (), selected=False, oracle=0)
        click(point(224, 150))
        check('folder', ('Documents', 'Date modified:', '1/1/2010', '1:05 PM'), ('File folder',), oracle=1)
        click(point(122, 74))
        wait_for(lambda: captions() == ['Documents'], 'Open navigates the existing window into Documents')
        check('opened-folder', ('0 items',), (), selected=False)
        key('KEY_LEFTALT', 'KEY_LEFT')
        wait_for(lambda: captions() == ['Classic-demo'], 'Back to parent after Open')
        click(point(600, 450 if scale == 1 else 365))
        assert ImageChops.difference(bare, check('back-cleared', ('7 items',), (), selected=False)).getbbox() is None

        click(point(224, 272))
        check('file', ('Alpha.txt', 'Date modified:', '1/2/2010', 'Date created:'),
              ('Plain text document', 'Size: 17 bytes'), oracle=3)
        click(point(146, 74))
        menu = snap('open-with')
        menu_text = read_text(menu, out, 'open-with-menu', region(86, 89, 305, 160), 6)
        assert 'Kate' in menu_text or 'Open With' in menu_text, menu_text
        key('KEY_ESC')
        click(point(122, 74))
        wait_for(lambda: any('Alpha.txt' in c for c in captions(KATE)), 'KIO opens Alpha.txt in Kate')
        focus_root()
        click(point(224, 272))
        key('KEY_LEFTSHIFT', 'KEY_RIGHT')
        check('files', ('2 items selected', '1/2/2010', '1/3/2010'), ('Size: 29 bytes',), oracle=4)
        click(point(122, 74))
        wait_for(lambda: any('Beta.txt' in c for c in captions(KATE)), 'KIO opens Beta.txt from multi-selection')
        focus_root()
        click(point(224, 150))
        key('KEY_LEFTSHIFT', 'KEY_RIGHT')
        check('folders', ('2 items selected', '1/1/2010', '1/4/2010'), (), oracle=2)
        click(point(122, 74))
        wait_for(lambda: {'Classic-demo', 'Documents', 'Downloads'} <= set(captions()), 'multi-Open keeps both folders and the parent')
        focus_root()
        click(point(600, 450 if scale == 1 else 365))
        assert ImageChops.difference(bare, check('deselected', ('7 items',), (), selected=False)).getbbox() is None

        # A metadata change in the real listing must refresh a still-selected item.
        click(point(224, 272))
        user(f'touch -t 201001051205 {folder}/Alpha.txt')
        check('metadata-changed', ('Alpha.txt', '1/5/2010'), ('Size: 17 bytes',))
        click(point(625, 40))
        vmctl.type_text(VM, 'Beta')
        check('filtered-out-selection', ('1 item',), (), selected=False)
    finally:
        # Only this disposable fixture's Explorer windows are running.
        user('pkill -u tester -x win7-explorer || true; pkill -u tester -x kate || true')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true')
    args = parser.parse_args()
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    initial = user('~/.local/bin/win7-classic status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    root = user('mktemp -d /tmp/w7-selection.XXXXXXXX')
    folder = f'{root}/Classic-demo'
    try:
        if initial != 'windows':
            toggle('windows')
        assert user('xdg-mime query default text/plain') == 'org.kde.kate.desktop', 'lab fixture requires Kate for text/plain'
        user(f'''mkdir -p {folder}/{{Documents,Downloads,Music,Pictures,Projects}}
printf 'Classic reference' > {folder}/Alpha.txt
printf 'Another file' > {folder}/Beta.txt
touch -t 201001011305 {folder}/Documents
touch -t 201001041305 {folder}/Downloads
touch -t 201001021305 {folder}/Alpha.txt
touch -t 201001031305 {folder}/Beta.txt''')
        checksum = user(f'sha256sum {folder}/*.txt')
        for scale in (1, 1.5):
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}; touch -t 201001021305 {folder}/Alpha.txt')
            exercise(args.out / f'scale-{scale:g}', scale, root)
        assert user(f'sha256sum {folder}/*.txt') == checksum
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}; rm -r {root}')
        if initial != 'windows':
            toggle(initial)
    print('PASS: actual Details and Open for empty, single and multiple selections at 100% and 150%')


if __name__ == '__main__':
    main()
