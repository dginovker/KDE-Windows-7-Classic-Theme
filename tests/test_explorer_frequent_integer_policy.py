#!/usr/bin/env python3
"""Verify native KDE integer and boolean opt-outs on the real Explorer taskbar."""
import argparse
import json
from pathlib import Path

from explorer_frequent_fixture import TREE, fixture, stash, stop_folder_explorers, unit
from lab import toggle, user, wait_for
from test_explorer_frequent import PROFILE, STATE, explorer, key, ocr, panel, popup
from test_explorer_frequent_privacy import CONFIG, GROUP, STORE, close, policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--packaged', action='store_true')
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    exe = '/usr/bin/win7-explorer' if args.packaged else '~/.local/bin/win7-explorer'
    switch = '/usr/bin/win7-classic' if args.packaged else '~/.local/bin/win7-classic'
    assert user(f'{switch} status') == 'current' and explorer() is None
    with fixture('Projects') as restore:
        restore.callback(user, 'systemctl --user restart plasma-kactivitymanagerd')
        stash(restore, STATE, 'history')
        stash(restore, PROFILE, 'profile')
        stash(restore, CONFIG, 'policy')
        restore.callback(toggle, 'current', packaged=args.packaged)
        restore.callback(stop_folder_explorers)
        toggle('windows', packaged=args.packaged)
        panel('w.writeConfig("launchers", ["applications:org.win7classic.explorer.desktop"]);')

        def visit():
            unit(restore, f'{exe} {TREE}/Projects')
            wait_for(lambda: (explorer() or ('',))[0] == 'Projects', 'Explorer lists Projects')
            close()

        policy('what-to-remember', '0')
        visit()
        visit()
        popup(out, 'allowed', 1, launcher=True)
        key('ESC')
        assert json.loads(user(f'cat "{STORE}"')) == [[f'{TREE}/Projects', 2]]
        user(f'cp "{STORE}" {TREE}/counts-before')

        policy('what-to-remember', '02')
        read = f'kreadconfig6 --include-globals --file kactivitymanagerd-pluginsrc --group {GROUP} --key what-to-remember'
        assert user(read) == '02'
        assert user(f'{read} --type int --default 99; printf "%s" "$?"') == '2'
        print('Native KDE KConfig reads the unchanged spelling 02 as mode 2 (Do not remember)')
        visit()
        user(f'cmp "{STORE}" {TREE}/counts-before')
        print('Real Explorer visit in mode 02 left the count file byte-identical')
        image, x, y = popup(out, 'leading-zero-denial', 0, launcher=True)
        assert ocr(out, 'closed-pin-actions', image, (x+28, y+3, x+225, y+48)) == [
            'Windows', 'Explorer', 'Unpin', 'this', 'program', 'from', 'taskbar']
        key('ESC')

        for invalid in ('2bad', '2147483648', '3'):
            policy('what-to-remember', invalid)
            popup(out, f'invalid-{invalid}', 0, launcher=True, unavailable=True)
            key('ESC')
            visit()
            user(f'cmp "{STORE}" {TREE}/counts-before')
        policy('what-to-remember', '0')
        popup(out, 'allowed-again', 1, launcher=True)
        key('ESC')
        print('02 is action-only; malformed, overflowing and unknown modes fail closed; history returns on opt-in')

        policy('what-to-remember', '1')
        policy('allowed-applications', '')
        policy('blocked-by-default', '1')
        read = f'kreadconfig6 --include-globals --file kactivitymanagerd-pluginsrc --group {GROUP} --key blocked-by-default'
        assert user(read) == '1'
        assert user(f'{read} --type bool --default false; printf "%s" "$?"') == '0'
        print('Native KDE KConfig reads blocked-by-default=1 as true')
        visit()
        user(f'cmp "{STORE}" {TREE}/counts-before')
        print('Real Explorer visit with the empty allowlist left the count file byte-identical')
        image, x, y = popup(out, 'boolean-exclusion', 0, launcher=True)
        assert ocr(out, 'boolean-exclusion-actions', image, (x+28, y+3, x+225, y+48)) == [
            'Windows', 'Explorer', 'Unpin', 'this', 'program', 'from', 'taskbar']
        key('ESC')

        policy('allowed-applications', 'org.win7classic.explorer')
        popup(out, 'boolean-allowed', 1, launcher=True)
        key('ESC')
        policy('blocked-by-default', 'tru')
        popup(out, 'invalid-boolean', 0, launcher=True, unavailable=True)
        key('ESC')
        visit()
        user(f'cmp "{STORE}" {TREE}/counts-before')
        print('Numeric boolean exclusion is action-only; a valid allowlist restores history; malformed boolean fails closed')


if __name__ == '__main__':
    main()
