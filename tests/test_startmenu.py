#!/usr/bin/env python3
"""Acceptance test for the Classic Start menu (issue #8), run from the host against the lab VM.

Structure (edges, separators, highlights, buttons, the pressed Start button with its focus rectangle) must equal
the Windows references pixel-for-pixel; icons, labels and the account picture are masked because the apps,
user and font differ.
"""
from pathlib import Path
import sys
import time

from PIL import Image

from lab import ROOT, VM, vmctl, user, toggle, kwin_script, windows, wait_for, install, shot

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-startmenu-test')
REF = ROOT / 'reference/screenshots'
MENU = (0, 295, 405, 756)
START = (0, 756, 56, 800)
# Content that legitimately differs, in screen coordinates (left, top, right, bottom exclusive).
LEFT_ITEMS = (9, 300, 251, 686)
ALL_PROGRAMS_LABEL = (40, 695, 250, 717)
AVATAR = (290, 298, 372, 372)
RIGHT_LABELS = [(264, y, 403, y + 32) for y in (373, 407, 441, 475, 512, 546, 583, 617, 651, 685)]
SEARCH_LABEL = (11, 725, 226, 744)
SEARCH_ICON = (228, 723, 253, 747)
SHUTDOWN_LABEL = (258, 724, 328, 744)
# Flag; label inside the dotted focus rectangle (Wine's bold Tahoma runs 1px wider, issue #11); the reference's
# mouse pointer, which sits on the Start button in every menu screenshot.
START_CONTENT = [(4, 762, 22, 796), (22, 764, 50, 794), (50, 774, 52, 785), (21, 776, 42, 800)]
NORMAL_MASKS = [LEFT_ITEMS, ALL_PROGRAMS_LABEL, AVATAR, SEARCH_LABEL, SEARCH_ICON, SHUTDOWN_LABEL, *RIGHT_LABELS, *START_CONTENT]


def differing(ours, reference, regions, masks):
    a, b = Image.open(ours).convert('RGB'), Image.open(reference).convert('RGB')
    bad = []
    for x0, y0, x1, y1 in regions:
        for y in range(y0, y1):
            for x in range(x0, x1):
                if not any(l <= x < r and t <= y < bt for l, t, r, bt in masks) and a.getpixel((x, y)) != b.getpixel((x, y)):
                    bad.append((x, y, a.getpixel((x, y)), b.getpixel((x, y))))
    return bad


def check(name, reference, masks, regions=(MENU, START)):
    shot(OUT / f'{name}.png')
    bad = differing(OUT / f'{name}.png', REF / reference, regions, masks)
    assert not bad, f'{name}: {len(bad)} pixels differ from {reference}, e.g. (x, y, ours, windows) {bad[:6]}'
    print(f'{name}: structure matches {reference}')


def menu_open():
    # The Start menu is a plasmashell popup: detect it by its 405x461 frame at the screen's bottom-left.
    shot(OUT / 'probe.png')
    image = Image.open(OUT / 'probe.png').convert('RGB')
    return image.getpixel((404, 400)) == (64, 64, 64) and image.getpixel((253, 400)) == (128, 128, 128)


def open_menu():
    vmctl.pointer(VM, 25, 777, 'left')
    wait_for(menu_open, 'Start menu open')
    time.sleep(0.5)


def close_menu():
    vmctl.keys(VM, 'KEY_ESC')
    wait_for(lambda: not menu_open(), 'Start menu closed')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    vmctl.start(VM)
    install()
    user('rm -rf ~/Classic-demo; mkdir -p ~/Classic-demo/{Documents,Downloads,Music,Pictures,Projects}')
    toggle('windows')
    user('systemd-run --user --collect -q dolphin --new-window ~/Classic-demo')
    wait_for(lambda: 'org.kde.dolphin' in windows(), 'Dolphin window')
    kwin_script('for (const w of workspace.windowList()) if (w.resourceClass == "org.kde.dolphin") '
                '{ w.frameGeometry = {x: 256, y: 120, width: 768, height: 560}; workspace.activeWindow = w; }')
    time.sleep(1)

    open_menu()
    vmctl.pointer(VM, 640, 790)  # off the menu, like the reference
    time.sleep(0.5)
    check('1-menu', 'w7-menu.png', NORMAL_MASKS)

    vmctl.pointer(VM, 230, 395)
    time.sleep(0.5)
    pointer = (229, 393, 248, 421)
    # Our third favorite is highlighted where Windows highlights Calculator; its icon and label are masked.
    check('2-hover-left', 'w7-menu-hover-left.png', [m for m in NORMAL_MASKS if m != LEFT_ITEMS] + [
        (9, 300, 251, 378), (9, 414, 251, 686), (11, 378, 247, 414), pointer])

    vmctl.pointer(VM, 390, 423)
    time.sleep(0.5)
    check('3-hover-right', 'w7-menu-hover-right.png', NORMAL_MASKS[:4] + [SEARCH_ICON, SHUTDOWN_LABEL, *START_CONTENT] + [
        (264, y, 403, y + 32) for y in (373, 441, 475, 512, 546, 583, 617, 651, 685)] + [(267, 415, 340, 430), (389, 421, 405, 447)])

    vmctl.pointer(VM, 85, 702, 'left')
    time.sleep(1)
    # Programs view: the white list and the highlighted Back row; list entries and labels are masked.
    check('4-programs', 'w7-programs.png', [(3, 298, 253, 676), (40, 695, 250, 717), (84, 700, 101, 725),
                                             AVATAR, SEARCH_LABEL, SEARCH_ICON, SHUTDOWN_LABEL, *RIGHT_LABELS, *START_CONTENT])
    vmctl.pointer(VM, 640, 790)
    time.sleep(0.3)
    shot(OUT / '4b-programs.png')
    folder_count = int(user('ls /usr/share/applications | wc -l'))
    assert folder_count > 0
    vmctl.pointer(VM, 85, 702, 'left')  # Back
    time.sleep(0.5)
    vmctl.pointer(VM, 640, 790)
    time.sleep(0.5)
    check('5-back', 'w7-menu.png', NORMAL_MASKS)
    print('All Programs opens the program list and Back returns')

    vmctl.type_text(VM, 'kate')
    time.sleep(2)
    # Search view: white results pane, group header with its rule, first result highlighted, wider search box.
    # The rule starts after the header text, whose width differs with the font (issue #11).
    check('6-search', 'w7-search.png', [(11, 303, 84, 324), (21, 325, 400, 347), (7, 347, 402, 719), (11, 725, 229, 744),
                                         (231, 723, 253, 747), SHUTDOWN_LABEL, *START_CONTENT])
    vmctl.keys(VM, 'KEY_ENTER')
    wait_for(lambda: 'org.kde.kate' in windows(), 'Kate launched from search + Enter', 30)
    assert not menu_open(), 'menu stayed open after launching'
    user('pkill -u tester -x kate; true')
    print('typing a search and pressing Enter launches the first result')

    open_menu()
    vmctl.keys(VM, 'KEY_DOWN')
    vmctl.keys(VM, 'KEY_DOWN')
    time.sleep(0.5)
    shot(OUT / '7-keyboard.png')
    vmctl.keys(VM, 'KEY_ENTER')
    wait_for(lambda: 'org.kde.dolphin' in [c for c, v in windows().items() if v[1]], 'Down Down Enter launches the second favorite (Dolphin)', 30)
    print('keyboard navigation launches the selected favorite')

    open_menu()
    vmctl.pointer(VM, 300, 423, 'left')  # Documents
    wait_for(lambda: any(v[0].startswith('Documents') for v in windows().values()), 'Documents opens in the file manager', 30)
    print('right column opens Documents')

    open_menu()
    close_menu()
    open_menu()
    vmctl.pointer(VM, 25, 777, 'left')
    time.sleep(1)
    assert not menu_open(), 'clicking Start while the menu is open must close it'
    vmctl.keys(VM, 'KEY_LEFTMETA')
    wait_for(menu_open, 'Meta key opens the menu')
    close_menu()
    print('Esc, Start and the Meta key open/close the menu')

    open_menu()
    vmctl.pointer(VM, 290, 734, "left")  # Shut down
    wait_for(lambda: any('logout' in c.lower() for c in windows()), 'Shut down asks for confirmation', 30)
    shot(OUT / '8-shutdown-prompt.png')
    # KDE's prompt shuts down by itself after 30 s, so cancel straight away with its Cancel button.
    vmctl.pointer(VM, 711, 544, 'left')
    wait_for(lambda: not any('logout' in c.lower() for c in windows()), 'confirmation cancelled')
    assert user('echo alive') == 'alive'
    print('Shut down asks before doing anything and can be cancelled')
    (OUT / 'probe.png').unlink()
    print('ALL START MENU CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
