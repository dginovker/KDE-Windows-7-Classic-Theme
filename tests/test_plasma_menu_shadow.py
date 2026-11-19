#!/usr/bin/env python3
"""#30: measure the real Plasma Shut down submenu, outside its unchanged window."""
import argparse
import json
import time
from pathlib import Path

from PIL import Image, ImageChops
from lab import ROOT, VM, kwin_query, shot, toggle, user, vmctl, wait_for

REF = ROOT / 'reference/screenshots'
SHUTDOWN = (340, 607, 449, 749)  # half-open, excludes the shadow


def native(out):
    def load(name):
        return Image.open(REF / f'w7-{name}.png').convert('RGB')

    start, submenu = load('menu'), load('shutdown-menu')
    taskbar, jump = load('taskbar'), load('explorer-jumplist')
    for name, base, opened, boxes in [
        ('Start', taskbar, start, [(405, 295, 415, 748), (0, 756, 405, 760)]),
        ('jump list', taskbar, jump, [(308, 518, 316, 755), (80, 757, 308, 760)]),
    ]:
        assert all(ImageChops.difference(base.crop(box), opened.crop(box)).getbbox() is None for box in boxes), name
        print(f'genuine Windows {name}: unchanged right/bottom underlay')

    l, t, r, b = SHUTDOWN
    surround = (l - 8, t - 8, r + 8, b + 8)
    start.crop(surround).save(out / 'native-start-underlay.png')
    submenu.crop(surround).save(out / 'native-shutdown.png')
    edge = [submenu.getpixel((r + dx, t + 40))[0] for dx in range(8)]
    assert edge == [142, 171, 212, 241, 252, 255, 255, 255], edge
    desktop = load('desktop-view-submenu')
    samples = {
        # The white native background gives lossless straight and cap alpha samples.
        'right': [(r + dx, y, gray) for dx, gray in enumerate(edge) for y in range(t + 10, b - 15)],
        'top-right cap': [(x, y, submenu.getpixel((x, y))[0]) for x in range(r, r + 8) for y in range(t, t + 10)],
        'bottom': [(x, b + dy, gray) for dy, gray in enumerate(edge) for x in range(l + 24, r - 8)],
        # Resolve the native corner alpha on white, then verify it against the Shutdown pair on blue.
        'bottom-right corner': [(r + dx, b + dy, desktop.getpixel((412 + dx, 563 + dy))[0] if dx < 5 and dy < 5 else 255)
                                for dx in range(8) for dy in range(8)],
        'no left/top shadow': [(l - 1, y, 255) for y in range(t + 28, b - 28)] + [(x, t - 1, 255) for x in range(l, r + 8)],
    }
    compare(samples, start, submenu, 'Windows 7 Shut down', tolerance=1)
    return samples


def compare(samples, underlay, opened, name, tolerance):
    for strip, points in samples.items():
        # The native reference determines alpha, not the KDE screenshot or a KDE-derived golden.
        error, worst = max((max(abs(a - round(c * gray / 255)) for a, c in
                                zip(opened.getpixel((x, y)), underlay.getpixel((x, y)))), (x, y))
                           for x, y, gray in points)
        print(f'{name} {strip}: {len(points)} exterior samples, max error {error} at {worst}', flush=True)
        assert error <= tolerance, (name, strip, error, worst)


def live(out, scale, samples):
    # Operator starts the lab and installs the exact candidate before running this test.
    assert user('~/.local/bin/win7-classic status') == 'current'
    assert json.loads(user('kscreen-doctor -j'))['outputs'][0]['scale'] == scale

    def key(code):
        vmctl.keys(VM, 'KEY_' + code)

    def pt(x, y, button=None):
        vmctl.pointer(VM, round(x * scale), round(y * scale), button)

    def snapshot(name):
        time.sleep(.4)
        path = out / f'{name}.png'
        shot(path)
        return Image.open(path).convert('RGB')

    def shell_frames():
        pid = int(user('systemctl --user show plasma-plasmashell.service -p MainPID --value'))
        assert pid > 0
        rows = kwin_query(f'for(const w of workspace.windowList()) if(w.pid=={pid}) '
                          'emit(w.pid,w.popupWindow,w.frameGeometry.x,w.frameGeometry.y,w.frameGeometry.width,w.frameGeometry.height);')
        return [(pid, popup, tuple(map(float, rect))) for pid, popup, *rect in rows]

    # KWin reports logical geometry snapped to an integer physical pixel at 150%.
    tolerance = 0 if scale == 1 else 1 / scale

    def same_geometry(actual, expected):
        return all(abs(a - e) <= tolerance for a, e in zip(actual, expected))

    def frame(w, h):
        matches = [entry for entry in shell_frames() if same_geometry(entry[2][2:], (w, h))]
        assert len(matches) <= 1, matches
        return matches[0] if matches else None

    def opened():
        return frame(109, 142)

    snapshot('current-before')
    assert not opened() and not frame(405, 461)
    try:
        toggle('windows')
        clean = snapshot('windows-underlay')
        pt(25, clean.height / scale - 23, 'left')
        wait_for(lambda: frame(405, 461), 'real plasmashell Start window')
        pid, _, (x, y, w, h) = frame(405, 461)
        start = snapshot('start-underlay')
        bounds = (round((x + w) * scale), round((y + 40) * scale), round((x + w + 10) * scale), round((y + h - 16) * scale))
        assert start.crop(bounds).tobytes() == clean.crop(bounds).tobytes(), 'Start itself acquired a shadow'

        pt(x + 335, y + 440, 'left')
        wait_for(opened, 'real plasmashell Shut down window')
        child = opened()
        print(f'plasmashell={pid}, Start={(x, y, w, h)}, Shut down={child}', flush=True)
        assert child[0] == pid and same_geometry(child[2], (x + 340, y + 312, 109, 142)), child
        l, t, width, _ = child[2]
        submenu = snapshot('shutdown-open')
        if scale == 1:
            dx, dy = int(l) - SHUTDOWN[0], int(t) - SHUTDOWN[1]
            translated = {strip: [(px + dx, py + dy, gray) for px, py, gray in points] for strip, points in samples.items()}
            compare(translated, start, submenu, 'Plasma Shut down at 100%', tolerance=2)
        else:
            # Fractional output scale is a logical-size test, not a genuine 144-DPI Windows oracle.
            ex, ey = round((l + width) * scale), round((t + 50) * scale)
            chain = [start.getpixel((ex + i, ey)) != submenu.getpixel((ex + i, ey)) for i in range(12)]
            assert chain in [[True] * count + [False] * (12 - count) for count in (7, 8, 9)], chain
            print(f'Plasma Shut down at {scale:g}×: {sum(chain)} contiguous exterior pixels')
        key('ESC')
        wait_for(lambda: not opened() and frame(405, 461), 'Esc returns from the child to Start')
        # Compare after dismissal on the same underlay while the parent remains alive.
        strip = (round((l + width) * scale), round((t + 20) * scale), round((l + width + 8) * scale), round((t + 70) * scale))
        assert snapshot('shutdown-escape').crop(strip).tobytes() == start.crop(strip).tobytes(), 'stale shadow after Escape'
        key('RIGHT')
        wait_for(opened, 'keyboard reopens the Shut down child')
        assert opened() == child
        assert snapshot('shutdown-reopen').crop(strip).tobytes() == submenu.crop(strip).tobytes(), 'changed shadow on reopen'
        shadow_click = (l + width + 2, t + 50)
        p = tuple(round(v * scale) for v in shadow_click)
        assert start.getpixel(p) != submenu.getpixel(p), 'outside click must hit a visible shadow pixel'
        pt(*shadow_click, 'left')
        wait_for(lambda: not opened() and not frame(405, 461), 'click in exterior shadow dismisses both menus')
        snapshot('shutdown-shadow-click')

        # Switching from a visible child goes through the normal plasmashell/profile replacement.
        pt(25, clean.height / scale - 23, 'left')
        wait_for(lambda: frame(405, 461), 'Start reopened before mode switch')
        pt(x + 335, y + 440, 'left')
        wait_for(opened, 'Shut down still open when switching to current')
        assert opened() == child
        snapshot('shutdown-before-switch')
    finally:
        toggle('current')
    snapshot('current-after')
    assert not opened() and not frame(405, 461), 'Classic windows persist after current-mode switch'
    print('PASS: real Plasma Shutdown geometry, overlap, external pixels, dismissal and reopen')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--oracle-only', action='store_true', help='check committed genuine Windows captures without using either VM')
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    samples = native(args.out)
    if not args.oracle_only:
        live(args.out, args.scale, samples)


if __name__ == '__main__':
    main()
