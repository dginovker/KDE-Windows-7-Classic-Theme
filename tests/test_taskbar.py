#!/usr/bin/env python3
"""Acceptance test for the Classic taskbar (issue #7), run from the host against the lab VM.

The Linux scene mirrors reference/screenshots/w7-taskbar.png: three pinned apps with the middle one running
and active. Every taskbar pixel must equal the reference except inside button faces and the tray, where icons
and text legitimately differ (different apps, fonts and tray icons).
"""
from pathlib import Path
import sys
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, vmctl, user, toggle, kwin_script, windows, wait_for, install, shot

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-taskbar-test')
REFERENCE = ROOT / 'reference/screenshots/w7-taskbar.png'
PANEL = (0, 756, 1280, 800)
FACE, SHADOW, WHITE = (212, 208, 200), (128, 128, 128), (255, 255, 255)
# Button faces in reference coordinates (left, top, right, bottom exclusive): icons and text legitimately differ.
CONTENT = [(4, 762, 52, 796), (65, 762, 109, 796), (115, 762, 271, 796), (277, 762, 321, 796)]
REFERENCE_TRAY_LEFT = 1106


def tray_left(image):
    """Left edge of the notification area's sunken frame; its width follows the tray icons it holds."""
    for x in range(700, 1277):
        if image.getpixel((x, 778)) == SHADOW and image.getpixel((x, 760)) == SHADOW and image.getpixel((x - 1, 778)) == FACE:
            return x
    raise AssertionError('no notification area frame found on the taskbar')


def expected_panel(left):
    """The reference taskbar with its notification area frame moved to start at `left`."""
    image = Image.open(REFERENCE).convert('RGB')
    image.paste(FACE, (min(left, REFERENCE_TRAY_LEFT), 758, 1280, 800))
    image.paste(SHADOW, (left, 760, 1277, 761))
    image.paste(SHADOW, (left, 760, left + 1, 797))
    image.paste(WHITE, (left, 797, 1278, 798))
    image.paste(WHITE, (1277, 760, 1278, 798))
    return image


def structure_diff(path):
    ours = Image.open(path).convert('RGB')
    left = tray_left(ours)
    diff = ImageChops.difference(ours.crop(PANEL), expected_panel(left).crop(PANEL))
    for box in CONTENT + [(left + 1, 761, 1277, 797)]:
        diff.paste((0, 0, 0), (box[0], box[1] - PANEL[1], box[2], box[3] - PANEL[1]))
    return [(x, y + PANEL[1]) for y in range(diff.height) for x in range(diff.width) if diff.getpixel((x, y)) != (0, 0, 0)]


def assert_matches_reference(path):
    pixels = structure_diff(path)
    assert not pixels, f'{path.name}: {len(pixels)} taskbar pixels differ from the reference outside button faces, e.g. {pixels[:8]}'


def click(x, y):
    vmctl.pointer(VM, x, y, 'left')
    vmctl.pointer(VM, 640, 600)  # hover changes launcher buttons, so park the pointer on the desktop


def explorer():
    return windows().get('org.win7classic.explorer')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    vmctl.start(VM)
    install()
    user('rm -rf ~/Classic-demo; mkdir -p ~/Classic-demo/{Documents,Downloads,Music,Pictures,Projects}')
    # Windows mode inherits the current task manager's pinned apps; pin three, like the reference's three icons.
    # The Dolphin pin becomes Explorer, which then runs as the middle button, as in the reference.
    user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "for (const w of panels()[0].widgets()) '
         'if (w.type == \\"org.kde.plasma.icontasks\\") { w.currentConfigGroup = [\\"General\\"]; '
         'w.writeConfig(\\"launchers\\", [\\"applications:firefox.desktop\\", \\"applications:org.kde.dolphin.desktop\\", '
         '\\"applications:org.kde.konsole.desktop\\"]); }"')
    toggle('windows')
    user('systemd-run --user --collect -q ~/.local/bin/win7-explorer ~/Classic-demo')
    wait_for(lambda: explorer() is not None, 'Explorer window')
    kwin_script('for (const w of workspace.windowList()) if (w.resourceClass == "org.win7classic.explorer") '
                '{ w.frameGeometry = {x: 256, y: 120, width: 768, height: 560}; workspace.activeWindow = w; }')
    vmctl.pointer(VM, 640, 600)
    time.sleep(2)
    shot(OUT / '1-taskbar.png')
    assert_matches_reference(OUT / '1-taskbar.png')
    print('taskbar structure matches the Windows 7 reference')

    click(190, 778)
    wait_for(lambda: explorer()[2], 'Explorer minimized by its task button')
    time.sleep(1)
    shot(OUT / '2-minimized.png')
    click(190, 778)
    wait_for(lambda: explorer()[1] and not explorer()[2], 'Explorer restored and active')
    print('task button minimizes and restores its window')

    click(86, 778)
    wait_for(lambda: 'firefox' in windows(), 'Firefox launched from its pinned button', 60)
    time.sleep(2)
    shot(OUT / '3-launched.png')
    user('pkill -u tester firefox; true')
    wait_for(lambda: 'firefox' not in windows(), 'Firefox closed')
    print('pinned button launches its app')

    click(27, 778)
    time.sleep(1.5)
    shot(OUT / '4-start.png')
    assert Image.open(OUT / '4-start.png').convert('RGB').getpixel((404, 400)) == (64, 64, 64), 'Start did not open the Start menu'
    vmctl.keys(VM, 'KEY_ESC')
    print('Start button opens the Start menu (tested in detail by test_startmenu.py)')

    showing = lambda: user('qdbus6 org.kde.KWin /KWin org.kde.KWin.showingDesktop')
    click(1269, 778)
    wait_for(lambda: showing() == 'true', 'Show Desktop')
    click(1269, 778)
    wait_for(lambda: showing() == 'false', 'windows back after Show Desktop')
    print('Show Desktop toggles')

    toggle('current')
    time.sleep(1)
    shot(OUT / '5-current.png')
    toggle('windows')
    kwin_script('for (const w of workspace.windowList()) if (w.resourceClass == "org.win7classic.explorer") workspace.activeWindow = w;')
    vmctl.pointer(VM, 640, 600)
    time.sleep(2)
    shot(OUT / '6-windows-again.png')
    assert_matches_reference(OUT / '6-windows-again.png')
    print('taskbar still matches after switching current -> windows')

    # Side-by-side image for the issue: reference taskbar above ours.
    reference = Image.open(REFERENCE).convert('RGB').crop(PANEL)
    ours = Image.open(OUT / '1-taskbar.png').convert('RGB').crop(PANEL)
    pair = Image.new('RGB', (1280, 44 * 2 + 4), 'white')
    pair.paste(reference, (0, 0))
    pair.paste(ours, (0, 48))
    pair.save(OUT / 'side-by-side.png')
    print('ALL TASKBAR CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
