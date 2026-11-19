#!/usr/bin/env python3
"""Validate the Classic Explorer hover row against a measured native #59 oracle."""
import argparse
import json
from pathlib import Path
import subprocess
import time

import libvirt
import libvirt_qemu

from PIL import Image, ImageChops

from lab import (VM, assert_portal_display, clipboard, close_test_apps, digest, executable, install,
                 shot, toggle, user, vmctl, wait_for, windows)
from test_explorer_task_icon import asset, compare, composite
from test_task_jump_list import EXPLORER, FACE
from test_upgrade import output_name

KATE = "org.kde.kate"

TIMINGS = ('enter_ms', 'expiry_ms', 'leave_ms', 'row_leave_ms', 'rearm_ms')
BEHAVIOR = ('activate_on_click', 'takes_focus', 'escape_dismisses')


def oracle(path):
    data = json.loads(path.read_text())
    for key in TIMINGS:
        value = data[key]
        if key == 'expiry_ms' and value == -1:
            continue
        assert (len(value) == 2 and 0 <= value[0] <= value[1] and value[1] - value[0] <= 500), (key, value)
    for key in BEHAVIOR:
        assert type(data[key]) is bool, (key, data[key])
    return data


def run(out, scale, expected, native, domain, packaged):
    px = lambda value: round(value * scale)
    # Match the project's 44-logical-pixel panel on the 1280x800 lab output.
    panel = 800 - px(44)
    move = lambda x, dy, button=None: vmctl.pointer(VM, px(x), panel + px(dy), button)
    prefix = f'{scale:g}x-'
    task, row, close = (193, 22), (190, -20), (245, -20)
    park = (60, -136)
    micro = (195, 23)

    def snap(name):
        path = out / (prefix + name + '.png')
        shot(path)
        return Image.open(path).convert('RGB')

    def crop(image):
        return image.crop((px(119), panel-px(47), px(273), panel))

    def visible(image):
        # The outer frame survives pointer exit even after the inner bevel and Close disappear.
        x = px(130)
        top = [image.getpixel((x, panel-px(46)+n)) for n in (-1, 0, 1)]
        return (image.getpixel((x, panel-px(36))) == FACE
                and (255, 255, 255) in top
                and image.getpixel((x, panel-1)) == (64, 64, 64))

    def close_visible(image):
        x, y, radius = px(245), panel-px(20), px(7)
        return any(r > 145 and r > g + 30 and r > b + 30
                   for r, g, b in image.crop((x-radius, y-radius, x+radius, y+radius)).get_flattened_data())

    def qmp(command, arguments):
        result = json.loads(libvirt_qemu.qemuMonitorCommand(domain, json.dumps({
            'execute': command, 'arguments': arguments}), 0))
        assert 'return' in result, result

    def point(x, dy):
        # Timestamp the real tablet event, without pointer()'s screenshot and post-event sleep.
        qmp('input-send-event', {'events': [
            {'type': 'abs', 'data': {'axis': axis, 'value': round((value + .5) * 32768 / size)}}
            for axis, value, size in (('x', px(x), 1280), ('y', panel + px(dy), 800))]})

    def click_task():
        point(*task)
        for down in (True, False):
            qmp('input-send-event', {'events': [{'type': 'btn', 'data': {'button': 'left', 'down': down}}]})
            if down:
                time.sleep(.08)

    ppm = (out / (prefix + 'sample.ppm')).resolve()

    def capture():
        # A PPM screendump avoids PNG compression inside the measured interval.
        a = time.monotonic()
        try:
            qmp('screendump', {'filename': str(ppm), 'format': 'ppm'})
            b = time.monotonic()
            with Image.open(ppm) as im:
                return a, b, im.convert('RGB')
        finally:
            ppm.unlink(missing_ok=True)

    def transition(name, action, timing, before):
        # Record both endpoints: event and screenshot can occur anywhere within their respective calls.
        now = time.monotonic
        lo, hi = expected[timing]
        start = now()
        action()
        end = now()
        captures = []
        # Leave room for the monitor round trip; the actual timestamps, not this
        # scheduling margin, certify that both observations are inside the oracle.
        margin = 65 if timing == 'rearm_ms' else 30
        for label, target in (('early', end + (lo + 1) / 1000), ('late', start + (hi - margin) / 1000)):
            time.sleep(max(0, target - now()))
            a, b, im = capture()
            captures.append((label, (a-end)*1000, (b-start)*1000, im))
        for label, a, b, im in captures:
            im.save(out / (prefix + name + '-' + label + '.png'))
            print(f'{prefix}{name} {label}: [{a:.1f}, {b:.1f}] ms, row={visible(im)}, Close={close_visible(im)}', flush=True)
        _, a, _, early = captures[0]
        _, _, b, late = captures[1]
        assert lo <= a and b <= hi, f'{name}: screenshots did not certify native {timing} [{lo}, {hi}]'
        assert visible(early) == before, f'{name}: row transitioned before native lower bound {lo} ms'
        assert visible(late) != before, f'{name}: row did not transition inside native upper bound {hi} ms'
        if before:
            assert not close_visible(early), f'{name}: Close still visible during pointer-leave grace'
        else:
            assert close_visible(late), f'{name}: Close missing while pointer is on task'
        return late, end

    def check_grace_reentry(name, target, timing):
        # Re-enter before native dismissal, then require Close before a fresh row could open.
        departure = time.monotonic()
        point(*park)
        time.sleep(.14)
        _, _, grace = capture()
        point(*target)
        reentered = time.monotonic()
        time.sleep(.12)
        _, returned_at, returned = capture()
        time.sleep(expected[timing][1] / 1000)
        _, _, stayed = capture()
        for label, im in (('grace', grace), ('returned', returned), ('stayed', stayed)):
            im.save(out / (prefix + name + '-' + label + '.png'))
            print(f'{prefix}{name} {label}: row={visible(im)}, Close={close_visible(im)}', flush=True)
        assert (reentered - departure) * 1000 < expected[timing][0], f'{name}: re-entry missed grace'
        assert (returned_at - reentered) * 1000 < expected['enter_ms'][0], f'{name}: screenshot could show a fresh row'
        assert visible(grace) and not close_visible(grace), f'{name}: grace did not hide only Close'
        assert visible(returned) and close_visible(returned), f'{name}: Close did not return on re-entry'
        assert visible(stayed) and close_visible(stayed), f'{name}: re-entry did not cancel dismissal'

    move(137, 22)
    time.sleep(1.1)
    assert not visible(snap('current')), 'Classic hover row in current mode'
    move(640 / scale, -90)
    toggle('windows', packaged=packaged)
    move(137, 22)
    time.sleep(1.1)
    pin = snap('closed-pin')
    yellow = (255, 255, 225)
    assert sum(c == yellow for c in pin.crop((px(75), panel-px(22), px(220), panel)).get_flattened_data()) >= px(180), 'closed pin no longer uses Classic InfoBackground'
    assert not visible(pin), 'closed pin incorrectly uses a window row'
    if scale == 1:
        art = asset('explorer', 32)
        compare(pin.crop((121, 763, 153, 795)), composite(art, FACE), art, 'closed Explorer pin artwork')

    move(640 / scale, -90)
    user(f'mkdir -p ~/Classic-demo; systemd-run --user --collect -q {executable("win7-explorer", packaged)} ~/Classic-demo')
    user('systemd-run --user --collect -q kate -n')
    wait_for(lambda: {EXPLORER, KATE} <= windows().keys(), 'Explorer plus unrelated Kate')
    def focus_kate():
        if not windows()[KATE][1]:
            move(355, 22, 'left')
        assert windows()[KATE][1], 'Kate task did not take focus'

    focus_kate()

    # Let the initial app maps finish before measuring an already running task.
    time.sleep(1)

    def display(name):
        point(*park)
        time.sleep(.9)
        return transition(name, lambda: point(*task), 'enter_ms', False)

    if scale == 1.5:
        # The stock Dock renderer’s cold 150% presentation is not a timing oracle.
        point(*park)
        time.sleep(.9)
        point(*task)
        time.sleep(1.15)
        assert visible(snap('cold-setup-visible')), '150% warm-up hover never opened'
        point(*park)
        time.sleep(.9)
        assert not visible(snap('cold-setup-dismissed')), '150% warm-up hover did not dismiss'
    img, t0 = display('stationary')
    if scale == 1:
        actual = crop(img)
        actual.save(out / '100-row.png')
        expected_art = native.crop((119, 709, 273, 756))
        expected_art.save(out / '96dpi-native-row.png')
        diff = ImageChops.difference(actual, expected_art)
        diff.paste((0, 0, 0), (20, 17, 114, 37))  # compare live icon/title separately
        assert diff.getbbox() is None, f'hover frame or genuine close art differs: {diff.getbbox()}'
        icon = actual.crop((20, 19, 36, 35))
        art = asset('folder', 16)
        compare(icon, composite(art, FACE), art, 'actual Explorer folder window icon')
        caption = actual.crop((40, 15, 113, 40))
        path = out / '100-row-title.png'
        caption.resize((caption.width*4, caption.height*4)).save(path)
        text = subprocess.check_output(['tesseract', str(path), 'stdout', '--psm', '7'], text=True).strip()
        assert text == 'Classic-demo', f'not the window title: {text!r}'
    else:
        y0, x1, y1 = 709, 273, 756
        # Fractional-scale raster rounding can move the bevel by one physical pixel.
        top = panel - px(y1 - y0)
        assert any(img.getpixel((px(130), y)) == (255, 255, 255) for y in range(top - 1, top + 2))
        assert img.getpixel((px(130), panel - 2)) == (64, 64, 64)
        assert img.getpixel((px(x1) - 1, top + px(12))) == (64, 64, 64)
        # The physical footprint of the native red pixels scales with the Close art.
        def red_bounds(im, box):
            region = im.crop(box)
            points = [divmod(i, region.width)[::-1] for i, (r, g, b) in enumerate(region.get_flattened_data())
                      if r > 145 and r > g + 30 and r > b + 30]
            assert points, 'Close artwork missing'
            xs, ys = zip(*points)
            return min(xs), min(ys), max(xs), max(ys)

        ref_box = (235, 726, 255, 746)
        actual_box = (px(ref_box[0]), panel - px(y1 - ref_box[1]), px(ref_box[2]), panel - px(y1 - ref_box[3]))
        assert all(abs(a - px(n)) <= 2 for a, n in zip(red_bounds(img, actual_box), red_bounds(native, ref_box))), 'scaled Close artwork bounds differ'
    expiry = expected['expiry_ms']
    if expiry == -1:
        time.sleep(max(0, t0 + 20 - time.monotonic()))
        assert visible(snap('still-dwelling')), 'row expired inside the measured 20-second dwell'
    else:
        time.sleep(max(0, t0 + expiry[1] / 1000 + .2 - time.monotonic()))
        assert not visible(snap('expired')), 'row outlived the measured dwell'

    display('focus')
    state = windows()
    assert not state[EXPLORER][1], 'hover alone activated the Explorer window'
    assert state[KATE][1] != expected['takes_focus'], 'hover keyboard focus differs from native oracle'

    display('leave-owner')
    transition('left-owner', lambda: point(*park), 'leave_ms', True)
    display('reenter-owner')
    check_grace_reentry('reenter-owner', task, 'leave_ms')

    display('click-away')
    # The wider 150% Explorer window covers the ordinary park point. Click bare desktop.
    move(20, -100, 'left')
    time.sleep(expected['leave_ms'][1] / 1000)
    assert not visible(snap('after-click-away')), 'row stuck after clicking away'
    focus_kate()

    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_N')
    vmctl.type_text(VM, 'focus oracle')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_F')
    vmctl.type_text(VM, 'find field token')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_A')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_C')
    assert clipboard() == 'find field token', 'Kate Find field not focused before Escape'
    display('escape')
    snap('kate-find-before-escape')
    vmctl.keys(VM, 'KEY_ESC')
    assert expected['escape_dismisses'], 'Windows Escape oracle changed'
    assert visible(snap('after-escape')), 'Wayland hover row intercepted Escape'
    assert windows()[KATE][1], 'Escape moved focus from Kate'
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_END')
    vmctl.type_text(VM, 'x')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_A')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_C')
    assert clipboard() == 'focus oraclex', 'Escape was not delivered to Kate’s Find toolbar'

    display('travel')
    move(193, 2)
    move(*row)
    entered = snap('entered-row')
    assert visible(entered) and close_visible(entered), 'row or Close missing after pointer travel from task'
    transition('left-row', lambda: point(*park), 'row_leave_ms', True)
    display('reenter-row')
    move(*row)
    check_grace_reentry('reenter-row', row, 'row_leave_ms')

    display('return-trip')
    point(*row)
    time.sleep(.65)
    assert visible(snap('direct-row')), 'direct pointer travel dismissed the row'
    point(193, 2)
    time.sleep(.12)
    point(*task)
    time.sleep(.65)
    assert visible(snap('returned-owner')), 'row dismissed traveling back via the panel lip'

    display('right-click')
    move(*task, 'right')
    jump = snap('jump-list')
    assert not visible(jump) and jump.getpixel((px(193), panel-px(94))) == (0, 0, 0), 'jump list and hover row did not hand off'
    vmctl.keys(VM, 'KEY_ESC')

    focus_kate()
    display('activate-row')
    move(*row)
    vmctl.button(VM, 'left', True)
    try:
        state = windows()
        print('activate press:', state)
        assert not state[EXPLORER][1], 'pressed but not released on row activated Explorer'
        assert state['org.kde.plasmashell'][1] and not state[KATE][1], 'pressed row did not transfer focus to the shell'
    finally:
        vmctl.button(VM, 'left', False)
    state = windows()
    assert not visible(snap('after-row-release')), 'row remains open after activation'
    assert state[EXPLORER][1] == expected['activate_on_click'], 'clicking the row did not follow native focus behavior'
    assert KATE in state and not state[KATE][2], 'Explorer row affected another window'

    focus_kate()
    # Each trial starts with the same inactive, visibly open task, then clicks it.
    for variant in ('stationary', 'micro', 'reentry', 'reentry-micro'):
        focus_kate()
        point(*park)
        time.sleep(.9)
        assert not visible(snap('before-click-' + variant))
        assert windows()[EXPLORER] == ('Classic-demo', False, False)
        point(*task)
        time.sleep(.12)
        point(*micro)
        time.sleep(.85)
        assert visible(snap('pre-click-' + variant)) and not windows()[EXPLORER][1]
        click_task()
        time.sleep(1.15)
        assert windows()[EXPLORER][1], 'task click did not activate Explorer'
        assert not visible(snap('stationary-after-click-' + variant)), 'row rearmed without motion after task click'
        if variant.startswith('reentry'):
            point(*park)
            time.sleep(.85)
            point(*task)
            time.sleep(1.15)
            assert not visible(snap('stationary-after-reentry-' + variant)), 'stationary re-entry rearmed the row'
        if variant == 'micro':
            point(*micro)
            time.sleep(1.15)
            assert not visible(snap('micro-without-exit')), 'motion rearmed the row without leaving first'
        elif variant == 'reentry-micro':
            transition('micro-after-reentry', lambda: point(*micro), 'rearm_ms', False)

    focus_kate()
    display('close-row')
    move(*close)
    vmctl.button(VM, 'left', True)
    try:
        state = windows()
        print('close press:', state)
        assert EXPLORER in state and not state[EXPLORER][1], 'close press changed Explorer before release'
        assert state['org.kde.plasmashell'][1] and not state[KATE][1], 'pressed Close did not transfer focus to the shell'
    finally:
        vmctl.button(VM, 'left', False)
    wait_for(lambda: EXPLORER not in windows(), 'row closes Explorer window only')
    assert windows()[KATE][1:] == (True, False), 'KWin did not reactivate the previous window after Close'
    assert not visible(snap('after-close-release')), 'row remains open after closing target'
    user('pkill -KILL -u tester -x kate || true')
    toggle('current', packaged=packaged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('oracle', type=Path, help='manually reviewed intervals and states from the native sequence')
    parser.add_argument('native', type=Path, help='archived genuine hover-task.png')
    parser.add_argument('--scales', nargs='+', type=float, choices=(1, 1.5), default=(1, 1.5))
    parser.add_argument('--packaged', action='store_true', help='test the installed system package on the disposable lab account')
    args = parser.parse_args()
    expected = oracle(args.oracle)
    native = Image.open(args.native).convert('RGB')
    args.out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    if args.packaged:
        assert_portal_display()
        close_test_apps()
        toggle('current', packaged=True)
        user('pacman -Qo /usr/bin/{win7-classic,win7-explorer} && '
             'test ! -d ~/.local/share/plasma/plasmoids/org.win7classic.taskbar && rm -rf ~/.local/state/win7-classic')
    else:
        install()
    connection = libvirt.open('qemu:///session')
    domain = connection.lookupByName(VM)
    output = output_name()
    user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "for (const w of panels()[0].widgets()) '
         'if (w.type == \\"org.kde.plasma.icontasks\\") { w.currentConfigGroup = [\\"General\\"]; '
         'w.writeConfig(\\"launchers\\", [\\"applications:org.kde.konsole.desktop\\", '
         '\\"applications:org.kde.dolphin.desktop\\"]); }"')
    try:
        for scale in args.scales:
            user(f'kscreen-doctor output.{output}.scale.{scale}')
            time.sleep(2)
            before = digest()
            run(args.out, scale, expected, native, domain, args.packaged)
            assert digest() == before, 'current panel/profile bytes changed'
    finally:
        user('pkill -x win7-explorer; pkill -KILL -u tester -x kate; true')
        user(f'kscreen-doctor output.{output}.scale.1')
        if user(f'{executable("win7-classic", args.packaged)} status') == 'windows':
            toggle('current', packaged=args.packaged)
        connection.close()


if __name__ == '__main__':
    main()
