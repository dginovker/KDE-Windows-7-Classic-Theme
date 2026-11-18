#!/usr/bin/env python3
"""Windows 7 Explorer (issue #19), driven with the mouse and keyboard in the lab VM.

Windows mode turns the pinned Dolphin into Explorer and makes Explorer open folders; Explorer copies, pastes,
renames, deletes to the trash, undoes, filters, creates folders, opens files and shows properties. Switching back
to current mode restores Dolphin.
"""
from hashlib import sha256
from pathlib import Path
import sys
import time

from PIL import Image

from lab import ROOT, VM, vmctl, user, toggle, install, shot, wait_for, kwin_query, kwin_script

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-explorer-test')
EXPLORER = 'org.win7classic.explorer'
# The window is placed where reference/screenshots/w7-explorer.png has Explorer.
GEOMETRY = '{x: 256, y: 120, width: 768, height: 560}'
SUB, FILE, THIRD = (477, 270), (594, 270), (711, 270)  # icon cells, folders sorted first
SEARCH, NEW_FOLDER, VIEW_MENU = (880, 160), (583, 194), (942, 194)


def captions(cls=EXPLORER):
    return [r[0] for r in kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass == "{cls}") emit(w.caption);')]


def open_folder(path):
    # As from the desktop: the session's environment (XDG_CURRENT_DESKTOP=KDE) decides the folder handler.
    user(f'systemd-run --user --collect -q kioclient exec {path}')


def exists(path):
    return user(f'test -e {path} && echo yes || echo no') == 'yes'


def click(xy, button='left'):
    vmctl.pointer(VM, *xy, button)


def double_click(xy):
    vmctl.pointer(VM, *xy)
    for down in (True, False, True, False):
        vmctl.button(VM, 'left', down)


def key(*codes):
    vmctl.keys(VM, *codes)
    time.sleep(0.6)


def clear_fixture_view(folder):
    # A repeated VM run should start at the default without clearing any other folder's preferences.
    group = sha256(f'file:///home/tester/{folder}'.encode()).hexdigest()
    user(f'for key in View Sort; do kwriteconfig6 --file win7-explorer-viewsrc --group {group} --key "$key" --delete || exit; done')


def explorer_at(folder):
    user(f'systemd-run --user --collect -q ~/.local/bin/win7-explorer {folder}')
    wait_for(lambda: Path(folder).name in captions(), f'Explorer at {folder}')
    kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}") {{ w.frameGeometry = {GEOMETRY}; workspace.activeWindow = w; }}')
    time.sleep(1)


def white(path, xy):
    return Image.open(path).convert('RGB').getpixel(xy) == (255, 255, 255)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    vmctl.start(VM)
    install()
    clear_fixture_view('w7x')
    clear_fixture_view('w7x/sub')
    user('pkill -f "^/home/tester/.local/bin/win7-explorer"; rm -rf ~/w7x ~/.local/share/Trash; mkdir -p ~/w7x/sub; echo hi > ~/w7x/a.txt')
    user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "for (const w of panels()[0].widgets()) '
         'if (w.type == \\"org.kde.plasma.icontasks\\") { w.currentConfigGroup = [\\"General\\"]; '
         'w.writeConfig(\\"launchers\\", [\\"applications:firefox.desktop\\", \\"applications:org.kde.dolphin.desktop\\"]); }"')
    # A user association that must survive the switch untouched, beside the folder handler Windows mode adds.
    user('printf "[Default Applications]\\ntext/plain=org.kde.kate.desktop;\\n" > ~/.config/mimeapps.list')
    before = user('sha256sum ~/.config/mimeapps.list 2>&1; kreadconfig6 --group Icons --key Theme; true')

    toggle('windows')
    # In Windows mode the Classic taskbar is the only applet with launchers.
    launchers = user('grep "^launchers=" ~/.config/plasma-org.kde.plasma.desktop-appletsrc')
    assert launchers == 'launchers=applications:firefox.desktop,applications:org.win7classic.explorer.desktop', launchers
    vmctl.pointer(VM, 640, 600)
    time.sleep(1)
    click((136, 778))  # the second launcher, formerly Dolphin
    wait_for(lambda: 'tester' in captions(), 'the pinned Explorer opens at home')
    user('pkill -f "^/home/tester/.local/bin/win7-explorer"; true')
    open_folder('~/w7x/sub')
    wait_for(lambda: 'sub' in captions(), 'opening a folder uses Explorer')
    user('pkill -f "^/home/tester/.local/bin/win7-explorer"; true')
    print('the pinned Dolphin became Explorer, and folders open in Explorer')

    explorer_at('~/w7x')
    shot(OUT / '1-explorer.png')
    click(FILE)
    key('KEY_LEFTCTRL', 'KEY_C')
    double_click(SUB)
    wait_for(lambda: 'sub' in captions(), 'double-click enters the folder')
    key('KEY_LEFTCTRL', 'KEY_V')
    wait_for(lambda: exists('~/w7x/sub/a.txt'), 'copy and paste')
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: 'w7x' in captions(), 'Alt+Left goes back')
    print('copy, enter folder, paste, back')

    click(FILE)
    key('KEY_F2')
    key('KEY_LEFTCTRL', 'KEY_A')
    vmctl.type_text(VM, 'b.txt')
    key('KEY_ENTER')
    wait_for(lambda: exists('~/w7x/b.txt') and not exists('~/w7x/a.txt'), 'F2 renames')
    click(FILE)
    key('KEY_DELETE')
    wait_for(lambda: not exists('~/w7x/b.txt') and exists('~/.local/share/Trash/files/b.txt'), 'Delete moves to the trash')
    key('KEY_LEFTCTRL', 'KEY_Z')
    wait_for(lambda: exists('~/w7x/b.txt'), 'Ctrl+Z restores from the trash')
    print('rename, delete to trash, undo')

    click(SEARCH)
    vmctl.type_text(VM, 'b.t')
    time.sleep(1.5)
    shot(OUT / '2-search.png')
    # Only b.txt is left, in the first cell; the second cell is empty.
    assert not white(OUT / '2-search.png', SUB) and white(OUT / '2-search.png', FILE), 'search did not hide the non-matching folder'
    key('KEY_LEFTCTRL', 'KEY_A')
    key('KEY_BACKSPACE')
    print('search box filters the folder')

    click(NEW_FOLDER)
    time.sleep(1.5)
    shot(OUT / '3-new-folder.png')
    key('KEY_LEFTCTRL', 'KEY_A')
    vmctl.type_text(VM, 'made')
    key('KEY_ENTER')
    wait_for(lambda: exists('~/w7x/made'), 'New folder creates a folder')
    time.sleep(1)
    assert captions() == ['w7x'], f'New folder should stay in w7x: {captions()}'
    print('New folder')

    FILE_NOW = THIRD  # made and sub now come first
    click(FILE_NOW, 'right')
    time.sleep(1)
    shot(OUT / '4-context-menu.png')
    key('KEY_ESC')
    double_click(FILE_NOW)
    wait_for(lambda: any(c not in (EXPLORER, 'plasmashell') for c, *_ in kwin_query('for (const w of workspace.windowList()) emit(w.resourceClass);')),
             'double-clicking a file opens it in its app', 30)
    user('pkill -u tester -x kate; pkill -u tester -x kwrite; true')
    print('right-click menu shown; double-click opens a file')

    click(VIEW_MENU)
    time.sleep(1)
    shot(OUT / '5-view-menu.png')
    for _ in range(3):  # Details, Tiles, Content are the last three entries
        key('KEY_UP')
    key('KEY_ENTER')
    time.sleep(1)
    vmctl.pointer(VM, 640, 700)
    shot(OUT / '6-details.png')
    click((520, 288))  # b.txt, the third row in Details view
    key('KEY_LEFTALT', 'KEY_ENTER')
    wait_for(lambda: any('Properties' in c and 'b.txt' in c for c in captions()), 'Alt+Enter shows the selected file’s Properties')
    shot(OUT / '7-properties.png')
    key('KEY_ESC')
    print('Details view, Properties')

    click((640, 450))
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: not captions(), 'Ctrl+W closes the window')
    print('Ctrl+W closes Explorer')

    user('pkill -f "^/home/tester/.local/bin/win7-explorer"; true')
    toggle('current')
    assert user('sha256sum ~/.config/mimeapps.list 2>&1; kreadconfig6 --group Icons --key Theme; true') == before, 'current mode file manager or icons not restored'
    open_folder('~/w7x/sub')
    # Dolphin starts cold here, right after plasmashell restarted.
    wait_for(lambda: 'org.kde.dolphin' in [r[0] for r in kwin_query('for (const w of workspace.windowList()) emit(w.resourceClass);')], 'current mode opens folders in Dolphin', 30)
    shot(OUT / '8-current-dolphin.png')
    user('pkill -u tester -x dolphin; true')
    print('current mode: Dolphin opens folders again; mimeapps and icon theme restored')
    print('ALL EXPLORER CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
