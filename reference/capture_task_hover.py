#!/usr/bin/env python3
"""Record the genuine Windows 7 Classic hover oracle (#59), 1280x800/96 DPI.

Requires the reference VM and native-bench CD. Start from the stock Classic,
Never Combine, large-icon fixture (IE, Explorer, WMP pins). No guest agent.
"""
import argparse
import json
from pathlib import Path
import time

from PIL import Image

from capture import VM, fixture, run_dialog, vmctl

TASK = (193, 778)
MICRO = (195, 779)
ROW = (193, 736)
CLOSE = (245, 736)
PARK = (60, 620)
EXPLORER_CLIENT = (900, 590)
TIMING_OFFSETS = (270, 350, 420, 490, 560, 630, 700, 775)


def input_events(events):
    vmctl.virsh('qemu-monitor-command', VM, json.dumps({
        'execute': 'input-send-event', 'arguments': {'events': events},
    }))


def point(xy):
    # Bracket the tablet input itself, not vmctl.pointer's screen-size probe and wait.
    input_events([{'type': 'abs', 'data': {'axis': axis, 'value': round((value + .5) * 32768 / size)}}
                  for axis, value, size in zip(('x', 'y'), xy, (1280, 800))])


def button(down):
    input_events([{'type': 'btn', 'data': {'button': 'left', 'down': down}}])


def sample(capture, start, offsets, prefix='at-'):
    for ms in offsets:
        time.sleep(max(0, start + ms / 1000 - time.monotonic()))
        capture(f'{prefix}{ms:05d}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path, help='new artifact directory')
    parser.add_argument('--row-after-ms', type=int, help='second pass: wait this measured time before testing actions')
    parser.add_argument('--other', nargs=2, type=int, metavar=('X', 'Y'), default=(150, 400),
                        help='safe click inside Notepad; confirm with the pre-action captures')
    args = parser.parse_args()
    args.out.mkdir(parents=True)
    log = []
    case, t0 = '', time.monotonic()

    def event(name, action):
        before = time.monotonic()
        action()
        after = time.monotonic()
        log.append([case, name, round((before-t0)*1000), round((after-t0)*1000)])
        return after

    def frame(name, shown=None, active=None):
        path = args.out / f'{case}-{name}.png'
        event(name, lambda: vmctl.virsh('screenshot', VM, str(path)))
        with Image.open(path) as image:
            im = image.convert('RGB')
        row = im.getpixel((130, 720)) == (212, 208, 200) and im.getpixel((130, 710)) == (255, 255, 255)
        explorer = im.getpixel((230, 780)) == (255, 255, 255)
        print(f'{case} {name}: row={row} Explorer foreground={explorer} Notepad caption={im.getpixel((980, 121))}', flush=True)
        assert shown is None or row == shown, f'{path}: unexpected row visibility'
        assert active is None or explorer == active, f'{path}: unexpected Explorer focus'
        if name == 'before' and active is False:
            assert im.getpixel((980, 121)) == (160, 195, 235), f'{path}: Notepad is not foreground'

    def motion(name, xy):
        return event(name, lambda: point(xy))

    def click(xy):
        motion('click-move', xy)
        event('press', lambda: button(True))
        time.sleep(.08)
        event('release', lambda: button(False))

    def reset(name, explorer=False):
        nonlocal case, t0
        case, t0 = name, time.monotonic()
        # Clicking the client avoids priming the task-click suppression under test.
        click(EXPLORER_CLIENT if explorer else args.other)
        motion('park', PARK)
        time.sleep(.9)
        frame('before', shown=False, active=explorer)

    def replay():
        nonlocal case
        for trial in range(3):
            reset(f'enter-{trial}')
            sample(frame, motion('enter', TASK), TIMING_OFFSETS)
            frame('open', shown=True, active=False)
            case = f'owner-leave-{trial}'
            sample(frame, motion('leave', PARK), TIMING_OFFSETS)
            frame('dismissed', shown=False)

            reset(f'row-leave-{trial}')
            motion('enter', TASK)
            time.sleep(.12)
            motion('wake', MICRO)
            time.sleep(.9)
            frame('owner-open', shown=True, active=False)
            motion('row', ROW)
            time.sleep(.2)
            frame('open', shown=True, active=False)
            sample(frame, motion('leave', PARK), TIMING_OFFSETS)
            frame('dismissed', shown=False)

        # Same inactive, already-open row and same 80 ms click as the KDE replay.
        for variant in ('stationary', 'micro', 'reentry', 'reentry-micro'):
            reset('post-click-' + variant)
            motion('enter', TASK)
            time.sleep(.12)
            motion('wake', MICRO)
            time.sleep(.85)
            frame('pre-click', shown=True, active=False)
            click(TASK)
            time.sleep(1.15)
            frame('stationary-after-click', active=True)
            if variant.startswith('reentry'):
                motion('leave', PARK)
                time.sleep(.85)
                motion('reentry', TASK)
                time.sleep(1.15)
                frame('stationary-after-reentry', active=True)
            if variant.endswith('micro'):
                sample(frame, motion('micro', MICRO), (350, 450, 550, 650, 750, 1100))
                frame('post-micro', active=True)

    vmctl.start(VM)
    fixture(PARK)
    run_dialog('notepad')
    time.sleep(1)
    try:
        replay()
        for is_active in (False, True):
            reset('dwell-active' if is_active else 'dwell-inactive', is_active)
            sample(frame, motion('enter', TASK), (850, 1800, 3000, 5000, 8000, 12000, 20000))
            sample(frame, motion('leave', PARK), TIMING_OFFSETS, prefix='leave-')
        if args.row_after_ms is not None:
            for name in ('leave-before-row', 'travel', 'activate', 'escape', 'click-away', 'jump-list', 'close'):
                reset(name)
                motion('enter-task-no-click', TASK)
                time.sleep(.18)
                motion('wake', MICRO)
                time.sleep(args.row_after_ms / 1000)
                frame('row-before-action', shown=True, active=False)
                if name in ('travel', 'activate', 'close'):
                    event('cross-panel-gap', lambda: vmctl.pointer(VM, TASK[0], 758))
                    event('enter-row-no-click', lambda: vmctl.pointer(VM, *(CLOSE if name == 'close' else ROW)))
                    frame('row-entered', shown=True, active=False)
                if name in ('leave-before-row', 'travel'):
                    start = event('leave-no-click', lambda: vmctl.pointer(VM, *PARK))
                else:
                    actions = {'activate': lambda: vmctl.button(VM, 'left', True),
                               'close': lambda: vmctl.button(VM, 'left', True),
                               'escape': lambda: vmctl.keys(VM, 'KEY_ESC'),
                               'click-away': lambda: vmctl.pointer(VM, *PARK, 'left'),
                               'jump-list': lambda: vmctl.pointer(VM, *TASK, 'right')}
                    start = event(name, actions[name])
                    if name in ('activate', 'close'):
                        frame('pressed')
                        start = event('release', lambda: vmctl.button(VM, 'left', False))
                sample(lambda stamp: frame('after-' + stamp), start, (0, 100, 250, 500, 1000, 2000))
                if name == 'jump-list':
                    vmctl.keys(VM, 'KEY_ESC')
    finally:
        (args.out / 'time-brackets.json').write_text(json.dumps(log, indent=2) + '\n')


if __name__ == '__main__':
    main()
