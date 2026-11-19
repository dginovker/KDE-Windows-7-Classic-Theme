#!/usr/bin/env python3
"""Exercise Explorer's production command-band choosers, not the context menus."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shlex
import subprocess
import time

from PIL import Image

from lab import VM, install, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, double_click, exists, key


def words(image, box):
    crop = image.crop(box).convert('L')
    crop = crop.resize((crop.width * 3, crop.height * 3))
    buf = BytesIO()
    crop.save(buf, format='PNG')
    return subprocess.check_output(['tesseract', 'stdin', 'stdout', '--psm', '6'], input=buf.getvalue(), stderr=subprocess.DEVNULL).decode()


def exercise(out, scale, root, explorer='~/.local/bin/win7-explorer'):
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
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={cfg} {explorer} {alpha}')
        wait_for(lambda: 'Alpha' in captions(), 'Explorer at Alpha')
        print(user(f'pid=$(systemctl --user show {unit}.service -p MainPID --value); '
                   'test "$pid" -gt 0 && readlink -f /proc/$pid/exe && sha256sum /proc/$pid/exe'))
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
        vmctl.pointer(VM, *pt(w - 128, 104))
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
    # The default Large Icons row now opens beside the command, not below it.
    labels = text(snap('command-view'), w - 98, 36, w + 47, 285)
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
    menu_image = snap('organize')
    rename_label = text(menu_image, 27, 277, 124, 293).strip()
    assert rename_label == 'Rename', f'Organize Rename row: {rename_label!r}'
    order = text(menu_image, 26, 89, 209, 331)
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
    layout_image = snap('layout')
    # OCR the highlighted first row separately from the dark-on-light rows beneath it.
    layout = text(layout_image, 241, 215, 409, 236) + text(layout_image, 232, 237, 409, 299)
    for label in ('Menu bar', 'Details pane', 'Preview pane', 'Navigation pane'):
        _, marker, layout = layout.partition(label)
        assert marker, (label, layout)
    key('KEY_M')
    bar = text(snap('visible-menu-bar'), 4, 57, 220, 80)
    assert all(label in bar for label in ('File', 'Edit', 'View', 'Tools', 'Help')), bar
    key('KEY_LEFTALT', 'KEY_T')
    key('KEY_F')
    wait_for(lambda: 'Folder Options' in captions(), 'menu bar Tools → Folder Options')
    key('KEY_LEFTALT', 'KEY_V')
    key('KEY_LEFTALT', 'KEY_H')
    key('KEY_ESC')
    assert not exists(f'{cfg}/win7-explorer-optionsrc')
    key('KEY_LEFTALT', 'KEY_T')
    key('KEY_F')
    wait_for(lambda: 'Folder Options' in captions(), 'Folder Options reopen')
    key('KEY_LEFTALT', 'KEY_V')
    snap('folder-options')
    key('KEY_LEFTALT', 'KEY_H')
    key('KEY_ENTER')
    wait_for(lambda: 'Folder Options' not in captions(), 'options accepted')
    assert 'ShowHidden=true' in user(f'cat {cfg}/win7-explorer-optionsrc')
    assert 'hidden' in text(snap('hidden-file'), 209, 108, 530, 264)
    organize(19)
    key('KEY_L')
    key('KEY_M')

    # Trigger the Organize proxy, not F2, and verify the selected file is renamed by KIO.
    click(pt(255, 251))  # Zulu, below Documents, Sample and .hidden in Content
    organize()
    key('KEY_N')
    wait_for(lambda: any('Rename' in title for title in captions()), 'Organize → Rename opens KIO')
    snap('organize-rename-dialog')
    key('KEY_LEFTCTRL', 'KEY_A')
    vmctl.type_text(VM, 'Zulu-renamed.txt\n')
    wait_for(lambda: exists(f'{alpha}/Zulu-renamed.txt') and not exists(f'{alpha}/Zulu.txt'), 'Organize Rename changes the real filename')
    print("PASS Organize → Rename: Zulu.txt → Zulu-renamed.txt")

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
    click(pt(53, 117))  # Copy shares a mnemonic with Cut and Close.
    go(beta, 'Beta')
    organize()
    click(pt(53, 134))  # Paste
    target = f'{beta}/Sample.txt'
    wait_for(lambda: exists(target), 'Organize Paste creates copy')
    assert user(f'cmp {alpha}/Sample.txt {target} && echo exact') == 'exact'
    organize()
    key('KEY_U')  # Undo
    wait_for(lambda: not exists(target), 'Organize Undo removes copy')
    organize()
    snap('redo-available')
    click(pt(53, 169))  # Redo shares a mnemonic with Properties.
    wait_for(lambda: exists(target), 'Organize Redo recreates copy')
    assert user(f'cmp {alpha}/Sample.txt {target} && echo exact') == 'exact'

    # The General option must affect actual KIO activation, not just remember a radio choice.
    go(alpha, 'Alpha')
    key('KEY_LEFTCTRL', 'KEY_E')
    vmctl.type_text(VM, 'Documents')
    options_file = f'{cfg}/win7-explorer-optionsrc'
    before = user(f'sha256sum {options_file}')

    def browse_options(choice, confirmation):
        organize()
        key('KEY_F')
        wait_for(lambda: 'Folder Options' in captions(), 'Organize → Folder and search options')
        key('KEY_LEFTALT', choice)
        key('KEY_SPACE')  # The mnemonic focuses the radio; Space checks it.
        snap(f'browse-folders-{choice}-{confirmation}')
        key(confirmation)
        wait_for(lambda: 'Folder Options' not in captions(), 'Folder Options dismissed')

    folder = pt(193, 118)  # first Content row, filtered to Documents
    def explicit_open(policy):
        click(folder, 'right')
        menu = snap(f'folder-item-open-{policy}')
        assert captions() == ['Alpha'], 'Explorer must survive opening the folder item menu'
        assert 'Open' in words(menu, (folder[0] + 12, folder[1], folder[0] + 140, folder[1] + 25))
        click((folder[0] + 40, folder[1] + 12))  # Open Folder With has the same mnemonic.

    browse_options('KEY_O', 'KEY_ESC')
    assert user(f'sha256sum {options_file}') == before
    double_click(folder)
    wait_for(lambda: captions() == ['Documents'], 'Cancel leaves folder activation in the starting window')
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: captions() == ['Alpha'], 'same-window Back still works')
    browse_options('KEY_O', 'KEY_ENTER')
    assert 'OpenFoldersInNewWindow=true' in user(f'cat {options_file}')
    # Re-enter the filter; folder navigation clears it, but opening a second window must not.
    key('KEY_LEFTCTRL', 'KEY_E')
    vmctl.type_text(VM, 'Documents')
    click(folder)
    key('KEY_ENTER')
    wait_for(lambda: sorted(captions()) == ['Alpha', 'Documents'], 'Enter opens a second Explorer window')
    snap('browse-folders-two-windows')
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: captions() == ['Alpha'], 'closing the child leaves the original window open')
    assert 'Documents' in text(snap('browse-folders-parent-retained'), w - 244, 31, w - 117, 50)
    explicit_open('new-window')
    wait_for(lambda: sorted(captions()) == ['Alpha', 'Documents'], 'explicit Open leaves parent and opens a new window')
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: captions() == ['Alpha'], 'explicit Open child closes, retaining its parent')
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: not captions(), 'last Explorer window closed before relaunch')
    launch()
    # Select an unambiguous item while the restored listing settles into its saved sort order.
    key('KEY_LEFTCTRL', 'KEY_E')
    vmctl.type_text(VM, 'Documents')
    wait_for(lambda: text(snap('browse-folders-relaunched-filter'), 72, 509, 316, 542).strip().replace(' ', '') == '1item',
             'relaunched listing filtered to the folder item')
    # The pointer was left over the closed window. Re-enter the new Wayland client
    # before sending the two clicks at the same coordinates.
    vmctl.pointer(VM, *pt(170, 280))
    double_click(folder)
    wait_for(lambda: sorted(captions()) == ['Alpha', 'Documents'], 'new window behavior survives relaunch')
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: captions() == ['Alpha'], 'child closes after relaunch')
    browse_options('KEY_S', 'KEY_ENTER')
    assert 'OpenFoldersInNewWindow=false' in user(f'cat {options_file}')
    explicit_open('same-window')
    wait_for(lambda: captions() == ['Documents'], 'explicit Open uses the same window after restoring Options')
    print("PASS explicit item Open: separate-window and same-window policies")
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: captions() == ['Alpha'], 'Back after explicit same-window Open')
    assert user(f'cmp ~/.config/kdeglobals {cfg}/kdeglobals && echo exact') == 'exact'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--explorer', type=Path, help='absolute path to the prebuilt Explorer in the lab (with --installed)')
    args = parser.parse_args()
    if args.explorer and (not args.installed or not args.explorer.is_absolute()):
        parser.error('--explorer requires --installed and an absolute guest path')
    explorer = shlex.quote(str(args.explorer)) if args.explorer else '~/.local/bin/win7-explorer'
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    switcher = '/usr/bin/win7-classic' if args.explorer == Path('/usr/bin/win7-explorer') else '~/.local/bin/win7-classic'
    original_mode = user(f'{switcher} status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    root = user('mktemp -d /tmp/w7-command-menus.XXXXXXXX')
    try:
        toggle('windows', executable=switcher)
        for scale in (1, 1.5):
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}')
            try:
                exercise(args.out / f'{scale:g}x', scale, root, explorer)
            finally:
                user(f'systemctl --user stop {Path(root).name}-{round(scale * 100)}.service', check=False)
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}; rm -r {root}')
        toggle(original_mode, executable=switcher)
    print('PASS: production View and Organize, Tiles/Content layouts and preferences, Folder Options and KIO Redo')


if __name__ == '__main__':
    main()
