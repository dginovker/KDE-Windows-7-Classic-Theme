#!/usr/bin/env python3
"""Recreate a named state in the Windows 7 reference VM and screenshot it.

  python reference/capture.py menu            # overwrite reference/screenshots/w7-menu.png
  python reference/capture.py menu --check    # fail unless the VM still renders the committed reference

Scenes start from the Classic-demo Explorer fixture (opened and positioned by
native-bench.exe on the VM's tools CD) and then click/type like a user would.
"""
import argparse
from pathlib import Path
import sys
import tempfile
import time

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'vm'))
import vmctl  # noqa: E402

VM = vmctl.VMS['w7']
TOOLS = r'D:\native-bench.exe'


def run_dialog(command):
    vmctl.keys(VM, 'KEY_LEFTMETA', 'KEY_R')
    time.sleep(1)
    vmctl.type_text(VM, command + '\n')


# Pointer positions match where it sat in each committed reference screenshot.
def fixture(pointer=(640, 790)):
    # Move off any menu first: Windows keeps the last hovered menu item highlighted.
    vmctl.pointer(VM, 640, 790)
    vmctl.keys(VM, 'KEY_ESC')
    run_dialog(TOOLS + ' --scene')
    time.sleep(4)
    run_dialog(TOOLS + ' --place')
    time.sleep(2)
    vmctl.pointer(VM, *pointer)


def start_menu():
    fixture()
    # Keyboard activation makes Start's focus cue independent of the previous scene.
    vmctl.keys(VM, 'KEY_LEFTMETA')
    time.sleep(0.5)
    vmctl.keys(VM, 'KEY_ESC')
    vmctl.pointer(VM, 25, 777, 'left')
    time.sleep(1.5)


def all_programs():
    start_menu()
    vmctl.pointer(VM, 85, 702, 'left')
    time.sleep(1.5)


def search():
    start_menu()
    vmctl.type_text(VM, 'calc')
    time.sleep(2)
    vmctl.pointer(VM, 640, 790)


def tray_popup(x, y=778):
    fixture()
    vmctl.pointer(VM, x, y, 'left')
    time.sleep(2)


# The clock and notification icons change with time and VM state, so they are excluded from comparisons.
LIVE_REGIONS = {'*': [(1100, 756, 1280, 800)], 'calendar': [(1150, 568, 1248, 704)]}


# Keep the notification frame and icons checkable; only its clock text is live.
CROPS = {'notification-area': (1100, 756, 1280, 800)}


def differing_pixels(a, b, scene='*'):
    diff = ImageChops.difference(Image.open(a).convert('RGB'), Image.open(b).convert('RGB'))
    regions = [(103, 7, 163, 39)] if scene == 'notification-area' else LIVE_REGIONS['*'] + LIVE_REGIONS.get(scene, [])
    for box in regions:
        diff.paste((0, 0, 0), box)
    return sum(1 for v in diff.convert('L').get_flattened_data() if v), diff.getbbox()


def pressed(x, y):
    """Hold the left button on (x, y); the scene's cleanup moves away before releasing so nothing activates."""
    vmctl.pointer(VM, x, y)
    vmctl.button(VM, 'left', True)
    time.sleep(1)


def double_click(x, y):
    vmctl.pointer(VM, x, y)
    for down in (True, False, True, False):
        vmctl.button(VM, 'left', down)


def explorer_in_documents(pointer=(849, 419)):
    """Explorer after opening Documents from the fixture folder, so Back is enabled."""
    fixture((849, 419))
    vmctl.pointer(VM, 849, 419, 'left')
    double_click(485, 265)
    time.sleep(2)
    vmctl.pointer(VM, *pointer)
    time.sleep(1)


def explorer_with_forward(pointer):
    """Back to the fixture folder after opening Documents, so Forward is enabled."""
    explorer_in_documents((277, 159))
    vmctl.pointer(VM, 277, 159, 'left')
    time.sleep(2)
    vmctl.pointer(VM, *pointer)
    time.sleep(1)


def maximized():
    fixture((640, 790))
    vmctl.pointer(VM, 993, 132, 'left')  # the fixture's Maximize button
    time.sleep(2)
    vmctl.pointer(VM, 640, 600)


def active_explorer():
    fixture((849, 419))
    vmctl.pointer(VM, 849, 419, 'left')


def explorer_file_context():
    # Fixed timestamps keep Explorer's selected-file details reproducible too.
    run_dialog('powershell -NoProfile -Command "'
               "$p=$env:USERPROFILE+'\\Classic-demo\\capture-reference.txt'; "
               "[IO.File]::WriteAllText($p,'Classic reference'); "
               "$f=Get-Item $p; $f.LastWriteTime='2010-01-01'; $f.CreationTime='2010-01-01'" + '"')
    time.sleep(4)
    active_explorer()
    vmctl.pointer(VM, 480, 375, 'right')
    time.sleep(1)


def context_menu(x, y):
    active_explorer()
    vmctl.pointer(VM, x, y, 'right')
    time.sleep(1)


def view_submenu(desktop=False, checked_hover=False):
    context_menu(120 if desktop else 849, 420 if desktop else 419)
    vmctl.pointer(VM, 220 if desktop else 940, 430)
    time.sleep(1.5)
    if checked_hover:
        vmctl.pointer(VM, 395 if desktop else 1105, 509 if desktop else 447)
        time.sleep(0.5)


def shutdown_button(arrow=False):
    start_menu()
    vmctl.pointer(VM, 335 if arrow else 315, 735, 'left' if arrow else None)
    time.sleep(2)


def shutdown_menu_selected():
    shutdown_button(arrow=True)
    vmctl.pointer(VM, 640, 790)
    for _ in range(4):
        vmctl.keys(VM, 'KEY_DOWN')
    time.sleep(0.5)


SCENES = {
    # w7-explorer.png also shows Start's keyboard-focus rectangle; recaptures lack it (60 pixels).
    'explorer': lambda: (fixture((849, 419)), vmctl.pointer(VM, 849, 419, 'left')),
    # Explorer active with the pointer off the taskbar: the plain taskbar target for issue #7.
    'taskbar': lambda: (fixture((849, 419)), vmctl.pointer(VM, 849, 419, 'left'), vmctl.pointer(VM, 640, 600)),
    'menu': start_menu,
    'programs': all_programs,
    # Hover states: pointer parked at the right end of the item so it covers as little as possible.
    'menu-hover-left': lambda: (start_menu(), vmctl.pointer(VM, 230, 395)),
    'menu-hover-right': lambda: (start_menu(), vmctl.pointer(VM, 390, 423)),
    'search': search,
    # Close button held down on the active fixture window (taskbar scene geometry).
    'close-pressed': lambda: (fixture((849, 419)), vmctl.pointer(VM, 849, 419, 'left'), pressed(1009, 132)),
    'maximized': maximized,
    # Same window after clicking the desktop, so its title bar is inactive.
    'inactive': lambda: (fixture((849, 419)), vmctl.pointer(VM, 849, 419, 'left'), vmctl.pointer(VM, 120, 420, 'left'), vmctl.pointer(VM, 640, 790)),
    # Explorer's Details view (picked from the view menu) and its Organize menu: file manager targets, issue #19.
    'explorer-details': lambda: (fixture((849, 419)), vmctl.pointer(VM, 849, 419, 'left'), vmctl.pointer(VM, 941, 194, 'left'),
                                 time.sleep(1), vmctl.pointer(VM, 1004, 325, 'left'), vmctl.pointer(VM, 849, 600), time.sleep(1)),
    'explorer-organize': lambda: (fixture((849, 419)), vmctl.pointer(VM, 849, 419, 'left'), vmctl.pointer(VM, 300, 193, 'left'), time.sleep(1)),
    # Back/Forward button states, which Explorer's Classic look renders differently from its raw bitmaps.
    'explorer-back': explorer_in_documents,
    # The pointer sits on each button's lower-right rim so it hides as little of the button as possible.
    'explorer-back-hot': lambda: explorer_in_documents((285, 167)),
    'explorer-back-pressed': lambda: (explorer_in_documents(), pressed(285, 167)),
    'explorer-forward': lambda: explorer_with_forward((849, 419)),
    'explorer-forward-hot': lambda: explorer_with_forward((313, 167)),
    'explorer-forward-pressed': lambda: (explorer_with_forward((849, 419)), pressed(313, 167)),
    # Same states with the pointer on the upper-left rim: together the two captures show every button pixel.
    'explorer-back-hot-ul': lambda: explorer_in_documents((268, 151)),
    'explorer-back-pressed-ul': lambda: (explorer_in_documents(), pressed(268, 151)),
    'explorer-forward-hot-ul': lambda: explorer_with_forward((296, 151)),
    'explorer-forward-pressed-ul': lambda: (explorer_with_forward((849, 419)), pressed(296, 151)),
    'calendar': lambda: tray_popup(1229),
    'volume': lambda: tray_popup(1187, 777),
    # The fixture VM pins Explorer between Internet Explorer and Windows Media Player.
    'explorer-jumplist': lambda: context_menu(190, 778),
    'explorer-file-context': explorer_file_context,
    'explorer-background-context': lambda: context_menu(849, 419),
    'desktop-context': lambda: context_menu(120, 420),
    'desktop-view-submenu': lambda: view_submenu(desktop=True),
    'explorer-view-submenu': view_submenu,
    'desktop-view-checked-hover': lambda: view_submenu(desktop=True, checked_hover=True),
    'explorer-view-radio-hover': lambda: view_submenu(checked_hover=True),
    'shutdown-hover': shutdown_button,
    'shutdown-menu': lambda: shutdown_button(arrow=True),
    'shutdown-menu-selected': shutdown_menu_selected,
    'notification-area': lambda: (active_explorer(), vmctl.pointer(VM, 640, 600)),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('scene', choices=SCENES)
    parser.add_argument('--out')
    parser.add_argument('--check', action='store_true')
    a = parser.parse_args()
    reference = Path(__file__).resolve().parent / 'screenshots' / f'w7-{a.scene}.png'
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp()) / reference.name if a.check else reference
    vmctl.start(VM)
    try:
        SCENES[a.scene]()
        vmctl.virsh('screenshot', VM, str(out))
        if a.scene in CROPS:
            with Image.open(out) as image:
                image.crop(CROPS[a.scene]).save(out, format='PNG')
    finally:
        vmctl.pointer(VM, 640, 600)
        vmctl.button(VM, 'left', False)
        vmctl.keys(VM, 'KEY_ESC')
        if a.scene == 'maximized':
            vmctl.pointer(VM, 1249, 8, 'left')  # Restore, so later scenes start from the normal fixture
        if a.scene.startswith(('explorer-back', 'explorer-forward')):
            vmctl.keys(VM, 'KEY_LEFTALT', 'KEY_F4')  # the navigated window; the next fixture opens a fresh one
        if a.scene == 'explorer-details':
            # Explorer remembers the view per folder; back to Large Icons for the other scenes.
            vmctl.pointer(VM, 941, 194, 'left')
            time.sleep(1)
            vmctl.pointer(VM, 1014, 62, 'left')  # the menu opens aligned to the current (Details) entry
        if a.scene in ('desktop-view-submenu', 'explorer-view-submenu', 'desktop-view-checked-hover', 'explorer-view-radio-hover'):
            vmctl.keys(VM, 'KEY_ESC')
        if a.scene.startswith('shutdown-menu'):
            vmctl.keys(VM, 'KEY_ESC')
        if a.scene == 'explorer-file-context':
            run_dialog('cmd /c del "%USERPROFILE%\\Classic-demo\\capture-reference.txt"')
            time.sleep(1)
        if a.scene == 'explorer-file-context':
            active_explorer()
            vmctl.pointer(VM, 640, 600)
    print(out)
    if a.check:
        count, box = differing_pixels(reference, out, a.scene)
        if count:
            sys.exit(f'{count} pixels differ from {reference.name} outside clock regions, within {box}')
        print(f'matches {reference.name} (clock regions excluded)')


if __name__ == '__main__':
    main()
