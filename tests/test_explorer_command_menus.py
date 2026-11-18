#!/usr/bin/env python3
"""Exercise Explorer's production command-band choosers, not the context menus."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import time

from PIL import Image

from lab import VM, install, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, exists, key


def words(image, box):
    crop = image.crop(box).convert('L')
    crop = crop.resize((crop.width * 3, crop.height * 3))
    buf = BytesIO()
    crop.save(buf, format='PNG')
    return subprocess.check_output(['tesseract', 'stdin', 'stdout', '--psm', '6'], input=buf.getvalue(), stderr=subprocess.DEVNULL).decode()


def exercise(out, scale, root):
    out.mkdir(parents=True, exist_ok=True)
    x, y, w, h = (256, 120, 768, 560) if scale == 1 else (42, 45, 730, 405)
    prefix = f'{root}/scale-{scale:g}'
    cfg, alpha, beta = [f'{prefix}/{name}' for name in ('config', 'Alpha', 'Beta')]
    unit = f'{Path(root).name}-{round(scale * 100)}'
    user(f'mkdir -p {cfg} {alpha}/Documents {beta}; cp ~/.config/kdeglobals {cfg}/; '
         f'printf "owned sample\n" > {alpha}/Sample.txt; : > {alpha}/Zulu.txt; : > {alpha}/.hidden')
    app = f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" && w.caption == "Alpha")'
    group = sha256(f'file://{alpha}'.encode()).hexdigest()

    def launch():
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={cfg} ~/.local/bin/win7-explorer {alpha}')
        wait_for(lambda: 'Alpha' in captions(), 'Explorer at Alpha')
        kwin_script(app + f' {{ w.frameGeometry={{x:{x},y:{y},width:{w},height:{h}}}; workspace.activeWindow=w; }}')

    def pt(xl, yl):
        return round((x + xl) * scale), round((y + yl) * scale)

    def snap(name):
        time.sleep(.5)
        path = out / (name + '.png')
        shot(path)
        with Image.open(path) as image:
            return image.convert('RGB')

    def text(im, left, top, right, bottom):
        return words(im, pt(left, top) + pt(right, bottom))

    def view():
        click(pt(w - 82, 74))
        vmctl.pointer(VM, 1170, 723)

    def choose(up):
        view()
        for _ in range(up):
            key('KEY_UP')
        key('KEY_ENTER')

    def organize(delta=0):
        click(pt(44, 74 + delta))
        vmctl.pointer(VM, 1170, 723)
        time.sleep(.3)

    def value():
        return user(f'XDG_CONFIG_HOME={cfg} kreadconfig6 --file win7-explorer-viewsrc --group {group} --key View')

    def content(name):
        image = snap(name)
        first = text(image, 215, 98, 400, 119)
        files = text(image, 211, 141, w - 10, 234)
        assert 'Documents' in first and 'Date modified' in files and 'Sample' in files and 'Size:' in files, (first, files)

    def go(folder, label):
        key('KEY_LEFTALT', 'KEY_D')
        vmctl.type_text(VM, folder + '\n')
        wait_for(lambda: label in captions(), f'navigation to {label}')

    launch()
    view()
    labels = text(snap('command-view'), w - 98, 88, w + 47, 285)
    expected = ['Extra Large Icons', 'Large Icons', 'Medium Icons', 'Small Icons', 'List', 'Details', 'Tiles', 'Content']
    tail = labels.replace('\n', ' ')
    for label in expected:
        _, marker, tail = tail.partition(label)
        assert marker, (scale, label, labels)
    key('KEY_ESC')
    choose(5)  # Small Icons
    assert value() == '3'
    small = snap('small-icons')
    assert 'Sample' in text(small, 400, 92, w - 10, 116)
    choose(4)  # List: the same labels now fill down the first column
    assert value() == '4'
    compact = snap('list')
    assert 'Sample' in text(compact, 170, 92, 390, 145)
    assert 'Sample' not in text(compact, 400, 92, w - 10, 145)
    choose(2)
    assert value() == '6'
    tiles = snap('tiles')
    assert 'Documents' in text(tiles, 215, 101, 393, 146)
    assert 'Sample' in text(tiles, 474, 101, w - 10, 146)
    assert 'folder' in text(tiles, 215, 101, 393, 146)
    click(pt(253, 120))
    choose(1)
    assert value() == '7'
    content('content')
    key('KEY_F2')
    snap('retained-selection-rename')
    assert any('Rename' in name for name in captions()), 'expected a KIO rename dialog'
    key('KEY_ESC')
    go(beta, 'Beta')
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: 'Alpha' in captions(), 'back to Alpha')
    content('content-back')
    click(pt(w - 110, 280))  # return keyboard focus to the file view after the modal dialog and navigation
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: 'Alpha' not in captions(), 'Explorer closed')
    launch()
    content('content-relaunched')
    if scale != 1:
        return

    # Empty selection: Properties works on the current folder, not on a phantom selection.
    organize()
    order = text(snap('organize'), 24, 90, 177, 336)
    for label in ['Cut', 'Copy', 'Paste', 'Undo', 'Redo', 'Select all', 'Layout', 'Folder and search options',
                  'Delete', 'Rename', 'Properties', 'Close']:
        _, marker, order = order.partition(label)
        assert marker, (label, order)
    click(pt(60, 302))
    wait_for(lambda: any('Alpha' in title and 'Properties' in title for title in captions()), 'current-folder Properties')
    snap('folder-properties')
    key('KEY_ESC')

    organize()
    key('KEY_L')
    snap('layout')
    key('KEY_M')
    bar = text(snap('visible-menu-bar'), 4, 57, 220, 80)
    assert all(label in bar for label in ('File', 'Edit', 'View', 'Tools', 'Help')), bar
    key('KEY_LEFTALT', 'KEY_T')
    key('KEY_F')
    wait_for(lambda: 'Folder Options' in captions(), 'menu bar Tools → Folder Options')
    key('KEY_LEFTALT', 'KEY_H')
    key('KEY_ESC')
    assert not exists(f'{cfg}/win7-explorer-optionsrc')
    key('KEY_LEFTALT', 'KEY_T')
    key('KEY_F')
    wait_for(lambda: 'Folder Options' in captions(), 'Folder Options reopen')
    snap('folder-options')
    key('KEY_LEFTALT', 'KEY_H')
    key('KEY_ENTER')
    wait_for(lambda: 'Folder Options' not in captions(), 'options accepted')
    assert 'ShowHidden=true' in user(f'cat {cfg}/win7-explorer-optionsrc')
    assert 'hidden' in text(snap('hidden-file'), 209, 108, 530, 264)
    organize(19)
    key('KEY_L')
    key('KEY_M')

    # Sort the same backing model; then Copy/Paste/Undo/Redo must change actual files.
    click(pt(460, 400), 'right')
    key('KEY_B')
    snap('content-sort-menu')
    click(pt(590, 526))  # Z-A in the existing Sort by submenu
    labels = text(snap('content-descending'), 214, 94, 470, 310)
    assert 0 <= labels.find('Zulu') < labels.find('Sample'), labels
    key('KEY_LEFTCTRL', 'KEY_E')
    vmctl.type_text(VM, 'Sample')
    time.sleep(.5)
    click(pt(245, 115))
    organize()
    click(pt(53, 117))  # Copy
    go(beta, 'Beta')
    organize()
    click(pt(53, 134))  # Paste
    target = f'{beta}/Sample.txt'
    wait_for(lambda: exists(target), 'Organize Paste creates copy')
    assert user(f'cmp {alpha}/Sample.txt {target} && echo exact') == 'exact'
    organize()
    click(pt(53, 153))  # Undo
    wait_for(lambda: not exists(target), 'Organize Undo removes copy')
    organize()
    snap('redo-available')
    click(pt(53, 169))  # Redo
    wait_for(lambda: exists(target), 'Organize Redo recreates copy')
    assert user(f'cmp {alpha}/Sample.txt {target} && echo exact') == 'exact'
    assert user(f'cmp ~/.config/kdeglobals {cfg}/kdeglobals && echo exact') == 'exact'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true')
    args = parser.parse_args()
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    original_mode = user('~/.local/bin/win7-classic status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    root = user('mktemp -d /tmp/w7-command-menus.XXXXXXXX')
    try:
        toggle('windows')
        for scale in (1, 1.5):
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}')
            try:
                exercise(args.out / f'{scale:g}x', scale, root)
            finally:
                user(f'systemctl --user stop {Path(root).name}-{round(scale * 100)}.service', check=False)
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}; rm -r {root}')
        toggle(original_mode)
    print('PASS: production View and Organize, Tiles/Content layouts and preferences, Folder Options and KIO Redo')


if __name__ == '__main__':
    main()
