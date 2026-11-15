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


def differing_pixels(a, b, scene='*'):
    diff = ImageChops.difference(Image.open(a).convert('RGB'), Image.open(b).convert('RGB'))
    for box in LIVE_REGIONS['*'] + LIVE_REGIONS.get(scene, []):
        diff.paste((0, 0, 0), box)
    return sum(1 for v in diff.convert('L').get_flattened_data() if v), diff.getbbox()


SCENES = {
    # w7-explorer.png also shows Start's keyboard-focus rectangle; recaptures lack it (60 pixels).
    'explorer': lambda: (fixture((849, 419)), vmctl.pointer(VM, 849, 419, 'left')),
    # Explorer active with the pointer off the taskbar: the plain taskbar target for issue #7.
    'taskbar': lambda: (fixture((849, 419)), vmctl.pointer(VM, 849, 419, 'left'), vmctl.pointer(VM, 640, 600)),
    'menu': start_menu,
    'programs': all_programs,
    'search': search,
    'calendar': lambda: tray_popup(1229),
    'volume': lambda: tray_popup(1187, 777),
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
    SCENES[a.scene]()
    vmctl.virsh('screenshot', VM, str(out))
    vmctl.keys(VM, 'KEY_ESC')
    print(out)
    if a.check:
        count, box = differing_pixels(reference, out, a.scene)
        if count:
            sys.exit(f'{count} pixels differ from {reference.name} outside clock regions, within {box}')
        print(f'matches {reference.name} (clock regions excluded)')


if __name__ == '__main__':
    main()
