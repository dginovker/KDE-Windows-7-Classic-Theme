#!/usr/bin/env python3
"""Read the source and supplied settings label from a real Classic balloon."""
import argparse
from pathlib import Path
import shlex

from PIL import Image

from lab import VM, kwin_query, shot, user, vmctl, wait_for
from test_tray import label, ocr

SENDER = '''from gi.repository import Gio, GLib
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
name = 'org.freedesktop.Notifications'
path = '/org/freedesktop/Notifications'
loop = GLib.MainLoop()

def call(method, signature, arguments):
    return bus.call_sync(name, path, name, method, GLib.Variant(signature, arguments),
                         None, Gio.DBusCallFlags.NONE, 5000, None)

def action(conn, sender, path, iface, signal, args):
    if args.unpack() == (notification, 'settings'):
        print('ActionInvoked', *args.unpack(), flush=True)
        call('CloseNotification', '(u)', (notification,))
        loop.quit()

bus.signal_subscribe(name, name, 'ActionInvoked', path, None, Gio.DBusSignalFlags.NONE, action)
notification, = call('Notify', '(susssasa{sv}i)', ('MailDesk', 0, 'dialog-information',
    'Inbox update', 'A new message arrived.', ['settings', 'Tune alerts'],
    {'x-kde-origin-name': GLib.Variant('s', 'Remote Workstation'),
     'x-kde-display-appname': GLib.Variant('s', 'MailDesk')}, 0)).unpack()
print('Notify', notification, flush=True)
loop.run()
'''


def main(out, scale):
    out.mkdir(parents=True, exist_ok=True)
    assert user('/usr/bin/win7-classic status') == 'windows'
    unit = 'w7-balloon-metadata-producer'
    vmctl.pointer(VM, 640, 380)
    user(f"systemd-run --user -q --unit={unit} /usr/bin/python -c " + shlex.quote(SENDER))

    def window():
        return [tuple(map(float, row)) for row in kwin_query(
            'for (const w of workspace.windowList()) if (w.notification) {const g=w.frameGeometry; emit(g.x,g.y,g.width,g.height);}')]

    def screenshot(name):
        file = out / f'{name}.png'
        shot(file)
        return Image.open(file).convert('RGB')

    def move(x, y, button=None):
        vmctl.pointer(VM, round(x * scale), round(y * scale), button)

    try:
        wait_for(window, 'Classic metadata balloon')
        rows = window()
        assert len(rows) == 1, rows
        x, y, w, h = rows[0]
        assert (w, h) == (272, 54), rows
        image = screenshot('balloon')
        assert image.getpixel((round((x + 190) * scale), round((y + 30) * scale))) == (255, 255, 225)
        move(x + 67, y + 15)
        region = tuple(round(v * scale) for v in (x + 70, y + 3, x + 200, y + 45))
        wait_for(lambda: {'MailDesk', 'Remote', 'Workstation'} <= {word for word, _ in ocr(screenshot('source-hover'), region)},
                 'application and origin in the title tooltip')
        move(x + 67, y + 15, 'right')
        menu = out / 'settings-menu.png'
        def settings_label():
            shot(menu)
            words = ocr(Image.open(menu))
            if {'Tune', 'alerts'} <= {word for word, _ in words}:
                return label(words, 'Tune')

        point = None

        def menu_visible():
            nonlocal point
            point = settings_label()
            return point

        wait_for(menu_visible, 'exact app-supplied Configure label')
        vmctl.pointer(VM, *point, 'left')
        wait_for(lambda: 'ActionInvoked ' in user(f'journalctl --user -u {unit} -b -o cat'), 'real settings action reached the sender')
        wait_for(lambda: not window(), 'sender closes its balloon after the settings action')
        print(user(f'journalctl --user -u {unit} -b -o cat'))
        print(f'{scale:g}x: MailDesk and Remote Workstation on hover; Tune alerts invokes settings; same opaque balloon.')
    finally:
        user(f'systemctl --user stop {unit}; systemctl --user reset-failed {unit} 2>/dev/null || true')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    args = parser.parse_args()
    main(args.out, args.scale)
