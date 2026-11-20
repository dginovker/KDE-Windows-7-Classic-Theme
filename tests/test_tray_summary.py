#!/usr/bin/env python3
"""Click Plasma's real Do Not Disturb summary in the packaged Windows tray."""
import argparse
from pathlib import Path

from PIL import Image

from lab import VM, shot, user, vmctl, wait_for
from test_tray import label, ocr
from test_tray_balloons import balloons


def main(out, scale, tray, default_action):
    out.mkdir(parents=True, exist_ok=True)
    assert user('/usr/bin/win7-classic status') == 'windows'
    assert not balloons()
    key = '--file plasmanotifyrc --group DoNotDisturb --key Until'
    assert not user(f'kreadconfig6 {key}'), 'start with Do Not Disturb off'
    nid = None
    point = (900, 630)

    def snap(tag):
        path = out / f'{tag}.png'
        shot(path)
        return Image.open(path).convert('RGB')

    def middle_click_tray():
        vmctl.pointer(VM, *tray, 'middle')
        vmctl.pointer(VM, *point)

    try:
        middle_click_tray()
        wait_for(lambda: user(f'kreadconfig6 {key}'), 'tray middle click enables Do Not Disturb')
        nid = int(user('notify-send -p -a Kate -t 0 -i dialog-information '
                       '-h string:desktop-entry:org.kde.kate "Deferred Canary" "Received during inhibition"'))
        print(f'Do Not Disturb enabled, real notification ID {nid}, mapped windows {balloons()}')
        assert not balloons()
        snap('suppressed')
        middle_click_tray()
        wait_for(lambda: not user(f'kreadconfig6 {key}'), 'tray middle click releases inhibition')
        wait_for(balloons, 'stock inhibition summary appears as a Classic balloon')
        frames = balloons()
        assert len(frames) == 1, frames
        x, y, w, h = frames[0]
        assert abs(w - 272) <= 1 / scale, frames
        box = tuple(round(v * scale) for v in (x, y, x + w, y + h))
        image = snap('summary')
        words = ocr(image, box)
        assert {'Unread', 'Notification', 'Show', 'Notifications'} <= {word for word, _ in words}, words
        assert image.getpixel((round((x + 4) * scale), round((y + h / 2) * scale))) == (255, 255, 225)
        action = 'Unread' if default_action else 'Show'
        click = label(words, action)
        print(f'Clicking {action!r} at physical {click}; summary logical geometry {frames[0]}')
        vmctl.pointer(VM, *click, 'left')
        wait_for(lambda: not balloons(), 'the summary action dismisses the balloon')

        def stock_history_contains_deferred():
            image = snap('after-action')
            region = (940, 315, 1279, 753) if scale == 1 else (780, 72, 1279, 753)
            words = ocr(image, region)
            return {'disturb', 'Deferred', 'Canary', 'inhibition'} <= {word for word, _ in words}

        wait_for(stock_history_contains_deferred, 'stock notification history with the Do Not Disturb control and deferred entry', 7)
        print('Stock history contains Do not disturb and the real deferred notification')
    finally:
        vmctl.pointer(VM, *point, 'left')
        if user(f'kreadconfig6 {key}'):
            middle_click_tray()
        if nid is not None:
            user('gdbus call --session -d org.freedesktop.Notifications -o /org/freedesktop/Notifications '
                 f'-m org.freedesktop.Notifications.CloseNotification {nid}', check=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    parser.add_argument('--tray', type=int, nargs=2, required=True, metavar=('X', 'Y'), help='physical coordinates of the live tray notification icon')
    parser.add_argument('--default-action', action='store_true', help='click the default title action instead of the named button')
    args = parser.parse_args()
    main(args.out, args.scale, args.tray, args.default_action)
