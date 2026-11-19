#!/usr/bin/env python3
"""Check centered and left-clamped jump lists and the task-owner cue at two scales."""
import argparse
from pathlib import Path
import time

from PIL import Image

from lab import VM, activate, install, kwin_script, shot, toggle, user, vmctl, wait_for, windows
from test_upgrade import output_name

EXPLORER = 'org.win7classic.explorer'
OTHER = 'org.kde.konsole'
FACE, WHITE, BLACK, NAVY = (212, 208, 200), (255, 255, 255), (0, 0, 0), (10, 36, 106)


def run(out, scale):
    tag = f'{scale:g}x'
    px = lambda x: round(x * scale)
    move = lambda x, y, button=None: vmctl.pointer(VM, px(x), 800 - px(y), button)
    toggle('windows')

    def capture(name):
        time.sleep(.45)
        path = out / f'{tag}-{name}.png'
        shot(path)
        return Image.open(path).convert('RGB')

    def frame(name, left, height):
        move(640 / scale, 150)
        img = capture(name)
        bottom = 800 - px(44)
        y = bottom - px(10)
        # Match a wide black-sided run of ButtonFace, not merely one dark pixel.
        row = [img.getpixel((x, y)) for x in range(1280)]
        edges = [i for i, c in enumerate(row) if c == BLACK]
        matches = [(a, b) for a, b in zip(edges, edges[1:]) if abs(b - a + 1 - px(230)) <= 2
                   and all(c == FACE for c in row[a+2:b-1])]
        assert len(matches) == 1, (name, 'jump list edges', matches)
        a, b = matches[0]
        assert abs(a - px(left)) <= 1, (name, 'wrong left edge', a, px(left))
        for logical_y in (44, 44 + height):
            expected = 800 - px(logical_y)
            assert any(img.getpixel(((a + b)//2, yy)) == BLACK for yy in range(expected-2, expected+2)), (
                name, 'wrong vertical edge (panel gap or height)', logical_y)
        return img

    def face(img, color):
        assert img.getpixel((px(245), 800 - px(20))) == color

    # First pin center 87 clamps left; Explorer pin center 137 fits without clamping.
    move(87, 21, 'right')
    frame('left-clamped', 0, 72)
    vmctl.keys(VM, 'KEY_ESC')
    move(137, 21, 'right')
    frame('closed-pin', 22, 72)
    vmctl.keys(VM, 'KEY_DOWN')
    hot = capture('keyboard-selection')
    assert hot.getpixel((px(220), 800 - px(90))) == NAVY, 'Down did not select the launch action'
    vmctl.keys(VM, 'KEY_ENTER')
    wait_for(lambda: EXPLORER in windows(), 'keyboard launches actual Explorer')
    user('systemd-run --user --collect -q konsole')
    wait_for(lambda: OTHER in windows(), 'unrelated Konsole window')
    # Give the click a point inside Konsole that remains exposed with Explorer active.
    kwin_script(f'for (const w of workspace.windowList()) {{ '
                f'if (w.resourceClass === "{OTHER}") w.frameGeometry = {{x: 480, y: 90, width: 320, height: 260}}; '
                f'if (w.resourceClass === "{EXPLORER}") w.frameGeometry = {{x: 10, y: 60, width: 450, height: 330}}; }}')
    activate(OTHER)
    regular = capture('inactive-before')
    face(regular, FACE)
    activate(EXPLORER)
    before = capture('active-before')
    face(before, WHITE)
    move(193, 21, 'right')
    active = frame('active-open', 78, 94)
    face(active, WHITE)
    caption = (px(153), 800-px(36), px(239), 800-px(8))
    assert active.crop(caption) == before.crop(caption), 'jump list changed the active caption'
    assert regular.crop(caption) != active.crop(caption), 'active and regular captions look identical'
    vmctl.keys(VM, 'KEY_ESC')
    after = capture('after-escape')
    assert after.getpixel((px(78), 800-px(54))) != BLACK, 'Escape did not dismiss'
    face(after, WHITE if windows()[EXPLORER][1] else FACE)

    activate(EXPLORER)
    move(193, 21, 'right')
    reopened = frame('active-reopened', 78, 94)
    face(reopened, WHITE)
    assert reopened.crop(caption) == before.crop(caption)
    vmctl.pointer(VM, px(600), px(220), 'left')
    wait_for(lambda: windows()[OTHER][1], 'click away gives Konsole focus')
    away = capture('after-click-away')
    assert away.getpixel((px(78), 800-px(54))) != BLACK, 'click-away did not dismiss'
    assert windows()[EXPLORER][1:] == (False, False), 'Explorer not live and inactive after click-away'
    face(away, FACE)
    assert away.crop(caption) == regular.crop(caption), 'click-away did not restore the regular caption'

    move(193, 21, 'right')
    face(frame('inactive-open', 78, 94), FACE)
    assert windows()[EXPLORER][1:] == (False, False), 'opening the list changed an inactive window'
    vmctl.keys(VM, 'KEY_ESC')
    activate(EXPLORER)
    move(193, 21, 'left')
    wait_for(lambda: windows()[EXPLORER][2], 'Explorer minimized')
    move(193, 21, 'right')
    face(frame('minimized-open', 78, 94), FACE)
    assert windows()[EXPLORER][2], 'opening the list restored a minimized window'
    vmctl.keys(VM, 'KEY_ESC')
    user('pkill -x win7-explorer; pkill -x konsole; true')
    toggle('current')
    print(f'{tag}: left clamp, centered pin/running list, real keyboard launch, Escape, '
          'active-to-inactive face and caption on click-away, inactive/minimized unchanged', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    output = output_name()
    user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "for (const w of panels()[0].widgets()) '
         'if (w.type == \\"org.kde.plasma.icontasks\\") { w.currentConfigGroup = [\\"General\\"]; '
         'w.writeConfig(\\"launchers\\", [\\"applications:org.kde.kate.desktop\\", '
         '\\"applications:org.kde.dolphin.desktop\\"]); }"')
    try:
        for scale in (1, 1.5):
            user(f'kscreen-doctor output.{output}.scale.{scale}')
            time.sleep(2)
            run(args.out, scale)
    finally:
        user('pkill -x win7-explorer; pkill -x konsole; true')
        user(f'kscreen-doctor output.{output}.scale.1')
        if user('~/.local/bin/win7-classic status') == 'windows':
            toggle('current')


if __name__ == '__main__':
    main()
