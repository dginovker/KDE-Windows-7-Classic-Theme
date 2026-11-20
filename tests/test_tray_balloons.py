#!/usr/bin/env python3
"""Exercise exact-package Classic balloon art and expiry under stack pressure."""
import argparse
import shlex
from pathlib import Path
import time

from PIL import Image

from lab import ROOT, VM, kwin_query, shot, user, vmctl, wait_for
from test_tray import ocr

SENDER = '''from gi.repository import Gio, GLib
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
name = "org.freedesktop.Notifications"
path = "/org/freedesktop/Notifications"
loop = GLib.MainLoop()
def call(method, args):
    return bus.call_sync(name, path, name, method, args, None, Gio.DBusCallFlags.NONE, 3000, None)
def send(title, body, urgency, timeout, replace=0):
    hints = {"desktop-entry": GLib.Variant("s", "org.kde.kate"), "urgency": GLib.Variant("y", urgency)}
    args = GLib.Variant("(susssasa{sv}i)", ("Kate", replace, "dialog-information", title, body, [], hints, timeout))
    return call("Notify", args).unpack()[0]
def closed(c, s, p, i, n, arg):
    print("Closed", *arg.unpack(), flush=True)
bus.signal_subscribe(name, name, "NotificationClosed", path, None, Gio.DBusSignalFlags.NONE, closed)
if __STACK__:
    hold = send("Persistent", "Persistent balloon body. " * 400, 2, 0)
    print("Persistent", hold, flush=True)
    def timed():
        print("Timed", send("Hidden Timed", "Must expire even when hidden under a persistent balloon.", 1, 4000), flush=True)
        return False
    GLib.timeout_add(1000, timed)
else:
    original = send("Original Notice", "One short notification body.", 1, 14000)
    print("Original", original, flush=True)
    def replace():
        updated = send("Updated Notice", "One short notification body.", 1, 7000, original)
        assert updated == original
        print("Replaced", updated, flush=True)
        return False
    GLib.timeout_add(4500, replace)
loop.run()
'''


def balloons():
    return [tuple(map(float, r)) for r in kwin_query('''for (const w of workspace.windowList()) {
        if (w.notification || w.criticalNotification) { const g = w.frameGeometry; emit(g.x,g.y,g.width,g.height); }
    }''')]


def main(out, scale, stack):
    out.mkdir(parents=True, exist_ok=True)
    assert user('win7-classic status') == 'windows'
    assert not balloons()
    unit = 'w734-balloon-proof'
    log = f'/tmp/{unit}.log'
    source = SENDER.replace('__STACK__', str(stack))

    def receipt():
        return user(f'cat {log}', check=False)

    def capture(tag):
        p = out / f'{tag}.png'
        shot(p)
        return Image.open(p).convert('RGB')

    def only_balloon():
        rows = balloons()
        assert len(rows) == 1, rows
        return rows[0]

    try:
        vmctl.pointer(VM, 300, 200)
        user(f'rm -f {log}; systemd-run --user --collect -q --unit={unit} '
             f'-p StandardOutput=append:{log} -p StandardError=append:{log} /usr/bin/python -c {shlex.quote(source)}')
        wait_for(balloons, 'the compositor maps a real notification')
        x, y, w, h = only_balloon()
        assert abs(w - 272) <= 1 / scale, (x, y, w, h)
        capture('original')
        if stack:
            assert h > 380, (x, y, w, h)
            wait_for(lambda: 'Timed ' in receipt(), 'the sender creates the second notification')
            timed_id = receipt().split('Timed ')[1].split()[0]
            ends = time.monotonic() + 8
            while time.monotonic() < ends:
                assert only_balloon() == (x, y, w, h), 'hidden timed balloon was actually visible'
                if f'Closed {timed_id} 1' in receipt().splitlines():
                    break
                time.sleep(.20)
            else:
                capture('stalled')
                raise AssertionError(f'hidden notification did not expire: {receipt()}')
            vmctl.pointer(VM, round((x + w / 2) * scale), round((y + 23) * scale), 'middle')
            wait_for(lambda: not balloons(), 'persistent balloon closes with no timed ghost behind it')
        else:
            assert abs(h - 54) <= 1 / scale, (x, y, w, h)
            pic = capture('balloon-art')
            assert pic.getpixel((round((x + 15) * scale), round((y + 30) * scale))) == (255, 255, 225)
            if scale == 1:
                native = Image.open(ROOT / 'reference/screenshots/w7-notification.png').convert('RGB')
                # Stock sender has a configurable desktop entry, so both buttons must be present.
                for name, x_ref, offset in [('configure', 1087, 234), ('close', 1100, 251)]:
                    target = native.crop((x_ref, 726, x_ref + 12, 741)).tobytes()
                    hits = [(dx, dy) for dx in range(offset - 5, offset + 6) for dy in range(4, 12)
                            if pic.crop((x + dx, y + dy, x + dx + 12, y + dy + 15)).tobytes() == target]
                    assert len(hits) == 1, f'{name}: genuine complete native button expected once, got {hits}'
                    print(f'{name}: exact genuine 12×15 px button at {hits[0]}')
            wait_for(lambda: 'Replaced ' in receipt(), 'the sender replaces the same notification ID')
            assert only_balloon() == (x, y, w, h)
            box = tuple(round(v * scale) for v in (x, y, x + w, y + h))
            wait_for(lambda: {'Updated', 'Notice'} <= {word for word, _ in ocr(capture('replaced'), box)}, 'updated text renders in place')
            nid = receipt().splitlines()[0].split()[1]
            wait_for(lambda: f'Closed {nid} 1' in receipt().splitlines(), 'updated notification expires')
            assert not balloons(), balloons()
        print(f'{scale=}, {stack=}, geometry {(x, y, w, h)}\n{receipt()}')
    finally:
        # Red regressions can leave a persistent notification in the real server.
        ids = [line.split()[1] for line in receipt().splitlines() if line.startswith(('Persistent ', 'Timed ', 'Original '))]
        for nid in ids:
            user(f'gdbus call --session -d org.freedesktop.Notifications -o /org/freedesktop/Notifications '
                 f'-m org.freedesktop.Notifications.CloseNotification {int(nid)}', check=False)
        user(f'systemctl --user stop {unit}; rm -f {log}', check=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('out', type=Path)
    p.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    p.add_argument('--stack', action='store_true')
    a = p.parse_args()
    main(a.out, a.scale, a.stack)
