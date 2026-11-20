#!/usr/bin/env python3
"""Drive the real Windows-mode Items editor and SNI registration/status signals."""
from pathlib import Path
import re
import shlex
import sys
import time

from PIL import Image

from lab import ROOT, VM, shot, user, vmctl, wait_for
from test_tray import APPLET_CONFIG, REFERENCE, icon_center, label, ocr

NORMAL = (231, 17, 187)
ATTENTION = (13, 227, 149)
STATUSES = ('Active', 'Passive', 'NeedsAttention')
STATE = '/tmp/w39-policy-status'
SCRIPT = '/tmp/w39-policy-sni.py'
LOG = '/tmp/w39-policy-sni.log'
UNIT = 'w39-policy-sni.service'
WATCHER = ('busctl --user get-property org.kde.StatusNotifierWatcher /StatusNotifierWatcher '
           'org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems')
POLICY_KEYS = ('shownItems', 'hiddenItems', 'disabledStatusNotifiers')


def run(out):
    assert user('win7-classic status') == 'windows'
    out.mkdir(parents=True, exist_ok=True)
    reference = Image.open(REFERENCE).convert('RGB')
    user('printf %s ' + shlex.quote((ROOT / 'tests/fixtures/tray_policy_sni.py').read_text()) + ' > ' + SCRIPT)

    def capture(name):
        shot(out / (name + '.png'))
        return Image.open(out / (name + '.png')).convert('RGB')

    def check_policy(index, show_all):
        def persisted():
            layout = user(f'cat {APPLET_CONFIG}')
            group = re.search(r'(?m)^(\[Containments\]\[\d+\]\[Applets\]\[\d+\])\n[^\[]*?^plugin=org\.win7classic\.tray$', layout)
            assert group, 'no Classic tray in the live config'
            settings = layout.split(group[1] + '[General]\n', 1)[1].split('\n[', 1)[0]
            values = dict(line.split('=', 1) for line in settings.splitlines() if '=' in line)
            stored = tuple(key for key in POLICY_KEYS if 'w39-policy' in values.get(key, '').split(','))
            expected = (POLICY_KEYS[index - 1],) if index else ()
            return stored == expected and (values.get('showAllItems') == 'true') == show_all

        wait_for(persisted, f'persisted SNI policy {index} with Show All={show_all}')
        print(f'persisted SNI policy {index}, Show All={show_all}', flush=True)

    active_address = None

    def start(status):
        nonlocal active_address
        stop()
        user(f'printf "%s\\n" {status} > {STATE}; systemd-run --user --quiet --unit={UNIT} '
             f'/bin/bash -c "python {SCRIPT} {STATE} > {LOG} 2>&1"')
        wait_for(lambda: 'Registered' in user(f'cat {LOG}', check=False), 'producer registration method returned')
        active_address = re.search(r'Registered (:\S+)', user(f'cat {LOG}'))[1] + '/StatusNotifierItem'
        wait_for(lambda: f'"{active_address}"' in user(WATCHER), f'watcher includes {active_address}')

    def stop():
        if user(f'systemctl --user is-active {UNIT} || true') == 'active':
            user(f'systemctl --user stop {UNIT}')
            if active_address:
                wait_for(lambda: f'"{active_address}"' not in user(WATCHER), f'watcher dropped {active_address}')

    def click(point, button='left'):
        vmctl.pointer(VM, *point, button)

    def key(code):
        vmctl.keys(VM, 'KEY_' + code)

    def colors(image, box):
        values = image.crop(box).getcolors(1280 * 800)
        return {rgb for n, rgb in values if n >= 196 and rgb in (NORMAL, ATTENTION)}

    def layout_test(name, status, slot, all_items=False):
        expected = {ATTENTION if status == 'NeedsAttention' else NORMAL}
        # A real hover tooltip can cover the tray frame when the rail shifts under the pointer.
        vmctl.pointer(VM, 810, 450)
        idle = capture(name + '-rail')
        assert colors(idle, (0, 750, 1280, 800)) == (expected if slot == 'rail' else set()), name
        if all_items:
            raw = reference.crop((13, 17, 18, 25)).tobytes()
            assert not any(idle.crop((x, y, x + 5, y + 8)).tobytes() == raw
                           for x in range(900, 1220) for y in range(766, 785)), 'show-all still has overflow'
        else:
            click(icon_center(idle, reference, (13, 17, 18, 25), tray_start=900))
            time.sleep(.35)
            opened = capture(name + '-popup')
            assert colors(opened, (750, 470, 1280, 750)) == (expected if slot == 'popup' else set()), name
            key('ESC')
            time.sleep(.25)
        print(name, status, slot, flush=True)

    def configure(policy, show_all=False, from_all=False):
        vmctl.pointer(VM, 810, 450)
        if from_all:
            idle = capture('before-show-all-off')
            click(icon_center(idle, reference, (77, 15, 93, 31), tray_start=900), 'right')
            time.sleep(.4)
            menu = ocr(capture('show-all-config-entry'), (850, 500, 1270, 766))
            click(label(menu, 'Notification'))
        else:
            click(icon_center(capture('before-items'), reference, (13, 17, 18, 25), tray_start=900), 'right')
        time.sleep(.5)
        if show_all or from_all:
            # Use the real checkbox; the policy row is below the fold.
            click(label(ocr(capture('show-all-checkbox'), (350, 60, 800, 92)), 'Show'))
        if policy is not None:
            click((1036, 600))  # scroll one page down, to the live SNI rows
            time.sleep(.35)
            settings = capture('items-' + str(policy))
            _, y = label(ocr(settings, (360, 100, 520, 668)), 'Policy')
            click((1015, y))
            time.sleep(.28)
            choice = ('relevant', 'Always', 'Only', 'Disabled')[policy]
            click(label(ocr(capture(f'choice-{policy}'), (887, 535, 1030, 636)), choice))
        time.sleep(.25)
        click((845, 681))  # OK in Plasma's 1280x800 configuration dialog
        time.sleep(.55)

    def change(status):
        user(f'printf "%s\\n" {status} > {STATE}')
        wait_for(lambda: user(f'tail -n1 {LOG}') in (status,) or user(f'tail -n1 {LOG}').endswith(' ' + status), status)
        time.sleep(.2)

    try:
        for index, (name, slots) in enumerate((
            ('relevant', ('rail', 'popup', 'rail')), ('always', ('rail',) * 3),
            ('only-popup', ('popup',) * 3), ('disabled', ('absent',) * 3),
        )):
            start('Active')
            if index:
                configure(index)
            check_policy(index, False)
            for status, slot in zip(STATUSES, slots):
                change(status)
                layout_test(name + '-' + status, status, slot)
                stop()
                time.sleep(.22)
                layout_test(name + '-unregistered-' + status, status, 'absent')
                start(status)
                time.sleep(.3)
                layout_test(name + '-reregistered-' + status, status, slot)
        for index in range(4):
            configure(index, show_all=True)
            check_policy(index, True)
            for status in STATUSES:
                change(status)
                layout_test(f'show-all-{index}-{status}', status, 'rail', all_items=True)
                stop()
                time.sleep(.22)
                layout_test(f'show-all-{index}-unregistered-{status}', status, 'absent', all_items=True)
                start(status)
                time.sleep(.3)
                layout_test(f'show-all-{index}-reregistered-{status}', status, 'rail', all_items=True)
            configure(None, from_all=True)
            check_policy(index, False)
            layout_test(f'show-all-{index}-off', STATUSES[-1], ('rail', 'rail', 'popup', 'absent')[index])
    finally:
        stop()
        user(f'rm -f {STATE} {LOG} {SCRIPT}')


if __name__ == '__main__':
    run(Path(sys.argv[1]))
