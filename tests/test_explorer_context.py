#!/usr/bin/env python3
"""Real Explorer background/item right-clicks and their KIO actions (issue #31)."""
import json
from pathlib import Path
import subprocess
import sys
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, vmctl, install, toggle, user, shot, wait_for, close_test_apps
from test_explorer import explorer_at, captions, click, double_click, key, exists, clear_fixture_view
from test_menus import popup_bevel

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-explorer-context-test')
BACKGROUND = (849, 419)


def popup(name, point=BACKGROUND):
    click(point, 'right')
    return capture_popup(name)


def capture_popup(name):
    vmctl.pointer(VM, 1100, 700)
    time.sleep(0.6)
    shot(OUT / f'{name}.png')
    image = Image.open(OUT / f'{name}.png').convert('RGB')
    box = popup_bevel(image)
    assert box, f'{name}: no real Explorer popup'
    crop = image.crop(box)
    crop.save(OUT / f'{name}-crop.png')
    crop.resize((crop.width * 3, crop.height * 3)).save(OUT / f'{name}-ocr.png')
    text = subprocess.check_output(['tesseract', str(OUT / f'{name}-ocr.png'), 'stdout', '--psm', '6'],
                                   stderr=subprocess.DEVNULL, text=True)
    (OUT / f'{name}.txt').write_text(text)
    return crop, box, text


def background(name):
    image, box, text = popup(name)
    labels = ['View', 'Sort by', 'Refresh', 'Paste', 'Paste shortcut', 'Undo', 'New', 'Properties']
    positions = [text.find(label) for label in labels]
    assert all(p >= 0 for p in positions) and positions == sorted(positions), f'wrong background menu: {text}'
    assert not any(label in text for label in ('Open', 'Delete', 'Rename', 'Group by')), text
    return image, box


def choose(row):
    # Keyboard mnemonics exercise the actual popup, not a copied action model.
    key('KEY_' + row)


def compare_native(image):
    native = Image.open(ROOT / 'reference/screenshots/w7-explorer-background-context.png').convert('RGB')
    # Retain the native frame and supported rows; omit unsupported Group by, customization and sharing.
    target = Image.new('RGB', (156, 169))
    bands = [(0, 36), (53, 70), (70, 79), (105, 139), (122, 139), (139, 148),
             (174, 191), (191, 200), (200, 221)]
    y = 0
    for top, bottom in bands:
        part = native.crop((849, 419 + top, 1005, 419 + bottom))
        target.paste(part, (0, y))
        y += bottom - top
    target.save(OUT / 'native-supported-rows.png')
    assert image.height == y, f'background height {image.height}, native supported rows {y}'
    # Removing Customize this folder shortens the menu: translate the right edge, never scale any pixels.
    assert 40 < image.width <= target.width, image.size
    aligned = Image.new('RGB', image.size)
    aligned.paste(target.crop((0, 0, image.width - 16, y)), (0, 0))
    aligned.paste(target.crop((140, 0, 156, y)), (image.width - 16, 0))
    aligned.save(OUT / 'native-aligned.png')
    diff = ImageChops.difference(image, aligned)
    # Only glyphs and the genuine pointer are excluded. Bevels, separators and arrows remain checked.
    for top in (2, 19, 36, 62, 79, 96, 122, 148):
        diff.paste((0, 0, 0), (19, top + 2, image.width - 14, top + 16))
    diff.paste((0, 0, 0), (0, 0, 19, 33))
    diff.save(OUT / 'background-structural-diff.png')
    (OUT / 'comparison.json').write_text(json.dumps({
        'reference': 'reference/screenshots/w7-explorer-background-context.png',
        'nativePopup': [849, 419, 1005, 640], 'supportedRowBands': bands,
        'actualSize': image.size, 'widthAlignment': 'translate rightmost 16px; no scaling',
        'textMasks': [[19, top + 2, image.width - 14, top + 16] for top in (2, 19, 36, 62, 79, 96, 122, 148)],
        'nativePointerMask': [0, 0, 19, 33], 'differenceBounds': diff.getbbox(),
        'scope': 'popup interior and frame; external compositor shadow excluded',
    }, indent=2))
    assert diff.getbbox() is None, f'background non-text pixels differ: {diff.getbbox()}'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    toggle('windows')
    clear_fixture_view('w7context')
    clear_fixture_view('w7context/sub')
    user('rm -rf ~/w7context; mkdir -p ~/w7context/sub; printf one > ~/w7context/a.txt; '
         'printf bigger-file > ~/w7context/z.txt; printf link-me > ~/w7context/sub/linked.txt')
    explorer_at('~/w7context')
    click((880, 160))
    vmctl.type_text(VM, 'plain-text')
    key('KEY_LEFTCTRL', 'KEY_A')
    key('KEY_LEFTCTRL', 'KEY_C')
    key('KEY_BACKSPACE')
    click(BACKGROUND)
    image, _ = background('background-no-selection')
    compare_native(image)
    for row in (62, 79):
        colors = set(image.crop((19, row + 2, image.width - 14, row + 16)).get_flattened_data())
        assert (128, 128, 128) in colors and (0, 0, 0) not in colors, 'non-URL clipboard enabled Paste/shortcut'
    choose('S')  # a disabled shortcut must not run a KIO job
    key('KEY_ESC')
    click((477, 270))
    background('background-after-selection')
    key('KEY_ESC')
    click(BACKGROUND)
    background('background-after-deselect')
    key('KEY_ESC')

    _, _, text = popup('item', (477, 270))
    assert all(label in text for label in ('Open', 'Delete', 'Rename', 'Properties')), text
    assert 'Sort by' not in text and 'Refresh' not in text, text
    key('KEY_ESC')
    # Keyboard context targets the focused item even with the pointer over empty space.
    key('KEY_HOME')
    key('KEY_COMPOSE')  # QEMU's PC context-menu key
    _, _, text = capture_popup('keyboard-item')
    assert 'Open' in text and 'Sort by' not in text, text
    key('KEY_ESC')
    print('real background menus before/after selection and deselection, item menu, native non-text pixels pass')

    background('sort-descending')
    choose('B')
    for _ in range(5):
        key('KEY_DOWN')
    key('KEY_ENTER')
    time.sleep(0.6)
    # With directories first, reverse order puts z.txt before a.txt in the second cell.
    _, _, text = popup('descending-item', (594, 270))
    assert 'Open' in text and 'Sort by' not in text, text
    key('KEY_ESC')
    key('KEY_LEFTALT', 'KEY_ENTER')
    wait_for(lambda: any('Properties' in c for c in captions()), 'sorted file Properties')
    shot(OUT / 'descending-file-properties.png')
    assert any('z.txt' in c for c in captions()), f'Sort descending did not reorder files: {captions()}'
    key('KEY_ESC')
    background('sort-ascending')
    choose('B')
    for _ in range(4):
        key('KEY_DOWN')
    key('KEY_ENTER')

    for name, steps, item in [('details', ('KEY_UP',), (480, 240)),
                              ('list', ('KEY_UP', 'KEY_UP'), (450, 220))]:
        background(f'{name}-view')
        choose('V')
        for step in steps:
            key(step)
        key('KEY_ENTER')
        time.sleep(0.6)
        background(f'{name}-background')
        key('KEY_ESC')
        _, _, text = popup(f'{name}-item', item)
        assert 'Open' in text and 'Sort by' not in text, text
        key('KEY_ESC')
    background('restore-large-icons')
    choose('V')
    key('KEY_DOWN')
    key('KEY_ENTER')
    time.sleep(0.6)
    print('Sort by changes the real listing; Details and List preserve background/item distinction')

    user('mkdir ~/w7context/refreshed')
    background('refresh')
    choose('E')
    time.sleep(0.6)
    double_click((477, 270))  # refreshed, sorted before sub
    wait_for(lambda: 'refreshed' in captions(), 'Refresh displays the newly created folder')
    key('KEY_LEFTALT', 'KEY_LEFT')
    user('rmdir ~/w7context/refreshed')
    time.sleep(0.6)

    background('new')
    choose('W')
    key('KEY_RIGHT')
    choose('F')
    time.sleep(0.8)
    key('KEY_LEFTCTRL', 'KEY_A')
    vmctl.type_text(VM, 'created')
    key('KEY_ENTER')
    wait_for(lambda: exists('~/w7context/created'), 'background New Folder')

    background('properties')
    choose('R')
    wait_for(lambda: any('Properties' in c for c in captions()), 'background folder Properties')
    assert any('Properties for w7context' in c for c in captions()), captions()
    shot(OUT / 'folder-properties.png')
    key('KEY_ESC')
    print('background Refresh, New Folder and current-folder Properties work')

    # Clipboard URLs originate in a real selected file, not a synthetic MIME fixture.
    double_click((594, 270))  # sub, after created
    wait_for(lambda: 'sub' in captions(), 'enter shortcut source folder')
    click((477, 270))
    key('KEY_LEFTCTRL', 'KEY_C')
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: 'w7context' in captions(), 'return to destination')
    background('paste-shortcut')
    choose('S')
    wait_for(lambda: user('readlink ~/w7context/linked.txt', check=False) == '/home/tester/w7context/sub/linked.txt',
             'Paste shortcut creates a symlink to the copied file')
    shot(OUT / 'shortcut-created.png')
    background('undo-shortcut')
    choose('U')
    wait_for(lambda: not exists('~/w7context/linked.txt'), 'background Undo removes shortcut')
    background('paste')
    choose('P')
    wait_for(lambda: user('test -f ~/w7context/linked.txt && test ! -L ~/w7context/linked.txt && cat ~/w7context/linked.txt',
                          check=False) == 'link-me', 'background Paste copies the file')
    background('undo-paste')
    choose('U')
    wait_for(lambda: not exists('~/w7context/linked.txt'), 'background Undo removes pasted file')
    close_test_apps()
    toggle('current')
    print('ALL EXPLORER CONTEXT CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
