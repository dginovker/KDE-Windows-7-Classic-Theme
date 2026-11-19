#!/usr/bin/env python3
"""Acceptance test for the Classic taskbar (issue #7), run from the host against the lab VM.

The Linux scene mirrors reference/screenshots/w7-taskbar.png: three pinned apps with the middle one running
and active. Every taskbar pixel must equal the reference except inside button faces and the tray, where icons
and text legitimately differ (different apps, fonts and tray icons).
"""
from pathlib import Path
import sys
import subprocess
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
    vmctl.pointer(VM, 137, 778)
    time.sleep(1.5)
    shot(OUT / '0-explorer-tooltip.png')
    tooltip = Image.open(OUT / '0-explorer-tooltip.png').convert('RGB')
    yellow = [(x, y) for y in range(700, 756) for x in range(60, 400) if tooltip.getpixel((x, y)) == (255, 255, 225)]
    assert yellow, 'pinned Explorer has no Classic tooltip'
    box = (min(x for x, y in yellow) - 1, min(y for x, y in yellow) - 1,
           max(x for x, y in yellow) + 2, max(y for x, y in yellow) + 2)
    assert box[3] - box[1] == 16, f'Classic tooltip should be 16px high, got {box}'
    for x in range(box[0], box[2]):
        assert tooltip.getpixel((x, box[1])) == (0, 0, 0), 'tooltip top border is not black'
        assert tooltip.getpixel((x, box[3] - 1)) == (0, 0, 0), 'tooltip bottom border is not black'
    # Reference tooltip in w7-explorer-back-hot.png uses InfoBackground, not the panel face.
    assert Image.open(ROOT / 'reference/screenshots/w7-explorer-back-hot.png').convert('RGB').getpixel((290, 190)) == (255, 255, 225)
    icon = Image.new('RGBA', (32, 32), FACE + (255,))
    icon.alpha_composite(Image.open(ROOT / 'explorer/assets/explorer-32.png').convert('RGBA'))
    icon_diff = ImageChops.difference(icon.convert('RGB'), tooltip.crop((121, 763, 153, 795)))
    assert max(high for low, high in icon_diff.getextrema()) <= 1, 'Explorer launcher does not show the genuine explorer.exe icon'
    tip = tooltip.crop((box[0] + 1, box[1] + 1, box[2] - 1, box[3] - 1))
    tip.resize((tip.width * 4, tip.height * 4)).save(OUT / 'tooltip-text.png')
    text = subprocess.check_output(['tesseract', str(OUT / 'tooltip-text.png'), 'stdout', '--psm', '7'], stderr=subprocess.DEVNULL, text=True).strip()
    assert text == 'Windows Explorer', f'Explorer launcher tooltip says {text!r}'
    print('pinned launcher shows the Classic Windows Explorer tooltip')
    vmctl.pointer(VM, 640, 600)
    user('systemd-run --user --collect -q ~/.local/bin/win7-explorer ~/Classic-demo')
    wait_for(lambda: explorer() is not None, 'Explorer window')
    kwin_script('for (const w of workspace.windowList()) if (w.resourceClass == "org.win7classic.explorer") '
                '{ w.frameGeometry = {x: 256, y: 120, width: 768, height: 560}; workspace.activeWindow = w; }')
    vmctl.pointer(VM, 640, 600)
    time.sleep(2)
    shot(OUT / '1-taskbar.png')
    assert_matches_reference(OUT / '1-taskbar.png')
    print('taskbar structure matches the Windows 7 reference')
    vmctl.pointer(VM, 190, 778, 'right')
    vmctl.pointer(VM, 640, 600)
    time.sleep(1)
    shot(OUT / '1-jumplist.png')
    jump = Image.open(OUT / '1-jumplist.png').convert('RGB').crop((78, 662, 308, 756))
    before = Image.open(OUT / '1-taskbar.png').convert('RGB')
    opened = Image.open(OUT / '1-jumplist.png').convert('RGB')
    assert before.crop((153, 762, 270, 796)) == opened.crop((153, 762, 270, 796)), 'opening the jump list changed the white face or bold caption'
    native_jump = Image.open(ROOT / 'reference/screenshots/w7-explorer-jumplist.png').convert('RGB').crop((78, 662, 308, 756))
    jump_diff = ImageChops.difference(jump, native_jump)
    # Our action-only popup has its own top border; native has the Frequent section above this block.
    jump_diff.paste((0, 0, 0), (0, 0, 230, 1))
    for top in (21, 43, 65):
        jump_diff.paste((0, 0, 0), (29, top, 222, top + 12))
    jump.save(OUT / 'jumplist-ours.png')
    native_jump.save(OUT / 'jumplist-native.png')
    jump_diff.point(lambda v: 255 if v else 0).save(OUT / 'jumplist-diff.png')
    assert jump_diff.getbbox() is None, f'jump-list action geometry/art differs: {jump_diff.getbbox()}'
    vmctl.keys(VM, 'KEY_ESC')
    print('jump-list action border, icon column and 22px rows match native pixels')
    vmctl.pointer(VM, 190, 778)
    time.sleep(1)
    shot(OUT / '1-window-tooltip.png')
    window_tip = Image.open(OUT / '1-window-tooltip.png').convert('RGB')
    assert window_tip.getpixel((130, 720)) == FACE and window_tip.getpixel((130, 710)) == WHITE
    assert window_tip.getpixel((241, 734)) == (153, 114, 112), 'running Explorer row has no native Close art'
    print('running Explorer shows the Classic window hover row')

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

    # Drag the running Explorer button past the Konsole launcher (issue #16).
    launchers = lambda: user('grep "^launchers=" ~/.config/plasma-org.kde.plasma.desktop-appletsrc')
    vmctl.pointer(VM, 190, 778)
    vmctl.button(VM, 'left', True)
    # Before any slot boundary, the dragged button already follows a small pointer motion.
    vmctl.pointer(VM, 207, 778)
    time.sleep(0.3)
    shot(OUT / '7-drag-follow.png')
    follow = Image.open(OUT / '7-drag-follow.png').convert('RGB')
    assert follow.getpixel((130, 760)) == (64, 64, 64), 'dragged button did not follow the pointer by 17 pixels'
    assert follow.getpixel((113, 760)) == FACE, 'dragged button remained stuck in its original slot'
    for x in range(217, 310, 10):
        vmctl.pointer(VM, x, 778)
    time.sleep(0.25)
    shot(OUT / '7-neighbour-slide.png')
    slid = Image.open(OUT / '7-neighbour-slide.png').convert('RGB')
    before = Image.open(OUT / '6-windows-again.png').convert('RGB')
    assert slid.crop((121, 763, 153, 795)) == before.crop((283, 763, 315, 795)), 'neighbour did not slide into the vacated slot'
    vmctl.button(VM, 'left', False)
    vmctl.pointer(VM, 640, 600)
    wait_for(lambda: launchers() == 'launchers=applications:firefox.desktop,applications:org.kde.konsole.desktop,'
             'applications:org.win7classic.explorer.desktop', 'dragging the Explorer button moves it after Konsole')
    time.sleep(1)
    shot(OUT / '7-dragged.png')
    assert not explorer()[2], 'releasing a drag also clicked the button (window minimized)'
    print('dragging a task button rearranges the taskbar and keeps the pinned order; a drag is not a click')

    # Right-click a running button, not the empty panel (issue #25).
    vmctl.pointer(VM, 240, 778, 'right')
    vmctl.pointer(VM, 640, 600)
    time.sleep(1)
    shot(OUT / '8-jumplist.png')
    menu = Image.open(OUT / '8-jumplist.png').convert('RGB')
    # The action block has the genuine reference's 230px width, 22px rows and black frame.
    left, top = 128, 662
    assert menu.getpixel((left, top + 10)) == (0, 0, 0), 'task right-click did not open the Classic jump list'
    reference_actions = Image.open(ROOT / 'reference/screenshots/w7-explorer-jumplist.png').convert('RGB').crop((78, 662, 308, 756))
    actions = menu.crop((left, top, left + 230, 756))
    diff = ImageChops.difference(actions, reference_actions)
    diff.paste((0, 0, 0), (0, 0, 230, 1))  # the reference has Frequent items above its action block
    for y in (16, 38, 60):
        diff.paste((0, 0, 0), (8, y, 222, y + 22))  # app-specific icons and text
    assert diff.getbbox() is None, f'jump-list action frame/spacing differs from Classic: {diff.getbbox()}'
    text_image = actions.resize((920, 376))
    text_image.save(OUT / 'jumplist-text.png')
    text = subprocess.check_output(['tesseract', str(OUT / 'jumplist-text.png'), 'stdout', '--psm', '6'], stderr=subprocess.DEVNULL, text=True)
    for label in ('Windows Explorer', 'Unpin this program from taskbar', 'Close window'):
        assert label in text, f'jump list missing {label!r}: {text!r}'
    # Escape dismisses without activating or closing the task.
    vmctl.keys(VM, 'KEY_ESC')
    assert explorer() is not None and not explorer()[2], 'Escape affected the window'
    vmctl.pointer(VM, 240, 778, 'right')
    vmctl.pointer(VM, left + 70, top + 71)
    time.sleep(0.4)
    shot(OUT / '8-close-hot.png')
    hot = Image.open(OUT / '8-close-hot.png').convert('RGB')
    assert hot.getpixel((left + 210, top + 65)) == (10, 36, 106), 'Close window does not hot-track with Classic highlight'
    click(left + 70, top + 71)
    wait_for(lambda: explorer() is None, 'Close window from the task jump list')
    print('Classic jump list matches the reference action frame and labels; Close window closes the actual window')

    # A launcher has launch + unpin, but no Close window. Unpin removes the saved pin.
    vmctl.pointer(VM, 187, 778, 'right')
    time.sleep(0.4)
    shot(OUT / '9-launcher-jumplist.png')
    click(72 + 80, 756 - 72 + 27)
    wait_for(lambda: explorer() is not None, 'jump-list application entry launches Explorer')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: explorer() is None, 'launched Explorer closes with Ctrl+W')
    vmctl.pointer(VM, 187, 778, 'right')
    time.sleep(0.4)
    click(72 + 80, 756 - 72 + 49)
    wait_for(lambda: 'org.win7classic.explorer.desktop' not in launchers(), 'launcher unpinned by jump list')
    user('systemd-run --user --collect -q ~/.local/bin/win7-explorer ~/Classic-demo')
    wait_for(lambda: explorer() is not None, 'unpinned Explorer running')
    vmctl.pointer(VM, 200, 778, 'right')
    time.sleep(0.4)
    shot(OUT / '10-unpinned-jumplist.png')
    vmctl.keys(VM, 'KEY_DOWN')
    vmctl.keys(VM, 'KEY_DOWN')
    vmctl.keys(VM, 'KEY_ENTER')
    wait_for(lambda: 'org.win7classic.explorer.desktop' in launchers(), 'running app pinned by jump list')
    toggle('current')
    toggle('windows')
    assert 'org.win7classic.explorer.desktop' in launchers(), 'jump-list pin did not persist across switching modes'
    print('launcher unpin and running-window pin work and persist')

    # Empty taskbar space still exposes Plasma panel configuration.
    vmctl.pointer(VM, 700, 778, 'right')
    time.sleep(0.7)
    shot(OUT / '11-panel-context.png')
    image = Image.open(OUT / '11-panel-context.png').convert('RGB')
    image.crop((700, 650, 1000, 756)).resize((1200, 424)).save(OUT / 'panel-context-text.png')
    text = subprocess.check_output(['tesseract', str(OUT / 'panel-context-text.png'), 'stdout', '--psm', '6'], stderr=subprocess.DEVNULL, text=True)
    assert 'Show Panel Configuration' in text, f'empty panel no longer offers configuration: {text!r}'
    vmctl.keys(VM, 'KEY_ESC')
    print('empty taskbar space still offers panel configuration')

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
