#!/usr/bin/env python3
"""Exercise the production Explorer and Start hover targets against the Windows 7 captures (#40)."""
import argparse
import json
from pathlib import Path
import time

from PIL import Image

from lab import ROOT, VM, install, shot, toggle, user, vmctl, wait_for
from test_explorer import captions, explorer_at
from test_explorer_details import read_text

REF = ROOT / 'reference/screenshots'
YELLOW = (255, 255, 225)
BLACK = (0, 0, 0)
BACK, FORWARD, SHUTDOWN = (285, 167), (313, 167), (315, 735)


def tip_box(image, area):
    crop = image.crop(area)
    mask = Image.new('L', crop.size)
    mask.putdata([255 if pixel == YELLOW else 0 for pixel in crop.get_flattened_data()])
    box = mask.getbbox()
    if box:
        x, y = area[:2]
        l, t, r, b = box
        return (x + l - 1, y + t - 1, x + r + 1, y + b + 1)


def exercise(out, scale):
    out.mkdir(parents=True, exist_ok=True)
    errors = []

    def snap(tag):
        path = out / (tag + '.png')
        shot(path)
        with Image.open(path) as image:
            assert image.size == (1280, 800), image.size
            return image.convert('RGB')

    def point(p):
        # The scale test keeps Explorer's top-left fixed in logical coordinates.
        return tuple(round(c * scale) for c in p)

    def move(p, button=None):
        vmctl.pointer(VM, *point(p), button)

    def hover(tag, pointer, area, reference, reference_area, text, *, above=None, expire=False, dismiss=None):
        start = time.monotonic()
        move(pointer)
        time.sleep(.2)
        assert not tip_box(snap(tag + '-early'), area), f'{tag} appeared before dwell'
        time.sleep(max(0, start + 1.15 - time.monotonic()))
        image = snap(tag)
        box = tip_box(image, area)
        if not box:
            errors.append(f'{tag}: tooltip absent after 1.15 s')
            if dismiss:
                dismiss()
            return
        native = tip_box(Image.open(REF / f'w7-{reference}.png').convert('RGB'), reference_area)
        assert native, reference
        l, t, r, b = box
        # Fractional Wayland placement rounds the pointer and frame; the edge of the solid fill
        # can also land one pixel inside a resampled border.
        slack = 2 if scale == 1 else 4
        assert abs(l - point(pointer)[0]) <= slack, box
        if above is None:
            assert abs(t - point(pointer)[1] - round(21 * scale)) <= slack, box
        else:
            assert abs(b - above) <= slack, box
        assert abs((b - t) - (native[3] - native[1]) * scale) <= 2, (tag, box, native)
        assert abs((r - l) - (native[2] - native[0]) * scale) <= 8 * scale, (tag, box, native)
        # Check all four sides at 1×, where no fractional resampling is involved.
        if scale == 1:
            for edge in [(l, t, r, t+1), (l, b-1, r, b), (l, t, l+1, b), (r-1, t, r, b)]:
                assert image.crop(edge).getcolors() == [((edge[2]-edge[0]) * (edge[3]-edge[1]), BLACK)], (tag, edge)
        label = read_text(image, out, tag + '-label', (l+2, t+2, r-2, b-2))
        assert label == text, (tag, label)
        print(f'{scale:g}x {tag}: {label!r}, frame {box}', flush=True)
        if expire:
            time.sleep(max(0, start + 6.25 - time.monotonic()))
        else:
            dismiss()
        assert not tip_box(snap(tag + '-dismissed'), area), f'{tag} did not dismiss'

    away = (600, 315)
    nav_ref = (265, 179, 760, 218)
    nav_area = (*point(nav_ref[:2]), *point(nav_ref[2:]))
    sx, sy = point((315, 0))[0], 800 - round(65 * scale)
    start_area = (sx-12, sy-round(48*scale), min(1280, sx+round(445*scale)), 800)
    start_bottom = 800 - round((65 + 12 + 3) * scale)  # 3 logical px above the button on Wayland
    # Start is anchored to the panel bottom, not to Explorer's top-left.
    shutdown = (315, sy / scale)
    for tag, pointer in [('back-disabled', BACK), ('forward-disabled', FORWARD)]:
        move(pointer, 'left')
        time.sleep(1)
        assert not tip_box(snap(tag), nav_area) and captions() == ['Classic-demo'], tag

    move((480, 265))
    for down in (True, False, True, False):
        vmctl.button(VM, 'left', down)
    wait_for(lambda: captions() == ['Documents'], 'Documents opens')
    hover('back', BACK, nav_area, 'explorer-back-hot', nav_ref, 'Back to Classic-demo', dismiss=lambda: move(away))
    hover('back-expiry', BACK, nav_area, 'explorer-back-hot', nav_ref, 'Back to Classic-demo', expire=True)
    move(BACK, 'left')
    wait_for(lambda: captions() == ['Classic-demo'], 'Back mouse action')
    move(away)
    hover('forward', FORWARD, nav_area, 'explorer-forward-hot', nav_ref, 'Forward to Documents',
          dismiss=lambda: vmctl.button(VM, 'left', True))
    vmctl.button(VM, 'left', False)
    wait_for(lambda: captions() == ['Documents'], 'Forward mouse action')
    for key, caption in [('KEY_LEFT', 'Classic-demo'), ('KEY_RIGHT', 'Documents')]:
        vmctl.keys(VM, 'KEY_LEFTALT', key)
        wait_for(lambda: captions() == [caption], f'Alt+{key} retains navigation')

    move(away)
    vmctl.keys(VM, 'KEY_LEFTMETA')
    time.sleep(.4)
    move((335, sy / scale))  # The split arrow is not the Shut down action.
    time.sleep(1)
    assert not tip_box(snap('shutdown-arrow'), start_area), 'Shut down explanation leaked onto the split arrow'

    def hover_shutdown(tag, **kwargs):
        hover(tag, shutdown, start_area, 'shutdown-hover', (305, 750, 750, 790),
              'Closes all open programs, shuts down Windows, and then turns off your computer.',
              above=start_bottom, **kwargs)

    hover_shutdown('shutdown', expire=True)
    move(away)
    hover_shutdown('shutdown-press', dismiss=lambda: vmctl.button(VM, 'left', True))
    move(away)
    vmctl.button(VM, 'left', False)  # cancelling the press must leave Start open
    hover_shutdown('shutdown-escape', dismiss=lambda: vmctl.keys(VM, 'KEY_ESC'))
    vmctl.keys(VM, 'KEY_ESC')
    assert not errors, '\n'.join(errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    parser.add_argument('--installed', action='store_true')
    args = parser.parse_args()
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    initial = user('~/.local/bin/win7-classic status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    folder = user('mktemp -d /tmp/w7-tool-tips.XXXXXXXX') + '/Classic-demo'
    assert not captions(), 'Close non-fixture Explorer windows before running this lab test'
    try:
        user(f'mkdir -p {folder}/Documents; kscreen-doctor output.{output["name"]}.scale.{args.scale}')
        if initial != 'windows':
            toggle('windows')
        explorer_at(folder)
        exercise(args.out, args.scale)
    finally:
        vmctl.keys(VM, 'KEY_ESC')
        vmctl.button(VM, 'left', False)
        vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: not captions(), 'fixture closed')
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}; rmdir {folder}/Documents {folder} {Path(folder).parent}')
        if initial != 'windows':
            toggle(initial)
    print('PASS: Explorer and Start tooltip checks')


if __name__ == '__main__':
    main()
