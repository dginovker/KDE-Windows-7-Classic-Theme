#!/usr/bin/env python3
"""Exercise live policy I/O failure and stale Frequent rows in the disposable lab."""
import argparse
import json
from pathlib import Path
import time

from PIL import Image

from lab import VM, shot, toggle, user, vmctl, wait_for
from test_explorer_frequent import BLACK, PROFILE, STATE, TREE, explorer, key, ocr, own_home_window, panel, popup
from test_explorer_frequent_privacy import CONFIG, GROUP, STORE, close, policy, start
from explorer_frequent_fixture import current, fixture, stash, stop_folder_explorers

LOWER = '$HOME/.config/kdedefaults'
LOWER_POLICY = f'{LOWER}/kactivitymanagerd-pluginsrc'


def reject_stale(out, name, x, y):
    vmctl.pointer(VM, x + 85, y + 43, 'left')
    time.sleep(.5)
    path = out / f'{name}-after.png'
    shot(path)
    with Image.open(path) as image:
        assert image.convert('RGB').getpixel((x, y)) != BLACK, f'{name}: old menu still showing'
    assert explorer() is None, f'{name}: the stale row opened Explorer'
    key('ESC')


def fast_unavailable(out, name, launcher=True):
    start = user('date +"%Y-%m-%d %H:%M:%S.%6N"')
    image, x, y = popup(out, name, 0, launcher=launcher, unavailable=True)
    assert ocr(out, name, image, (x + 5, y + 3, x + 170, y + 42)) == ['Frequent', 'Frequent', 'unavailable']
    journal = user(f"journalctl --user -u plasma-plasmashell --since '{start}' --no-pager")
    assert 'Frequent unavailable: could not check privacy or read history' in journal, journal


def main(out, scenario):
    out.mkdir(parents=True, exist_ok=True)
    assert user('~/.local/bin/win7-classic status') == 'current'
    assert '/home/tester/.config/kdedefaults:' in user('systemctl --user show-environment | grep ^XDG_CONFIG_DIRS=')
    original_mode = user(f'stat -c %a "{LOWER}"')
    assert explorer() is None, 'the Explorer task button must belong to the test'
    with fixture('Projects', 'Once') as restore:
        restore.callback(user, 'systemctl --user restart plasma-kactivitymanagerd')
        for path, name in ((STATE, 'history'), (PROFILE, 'profile'), (CONFIG, 'policy'), (LOWER_POLICY, 'lower')):
            stash(restore, path, name)
        restore.callback(current)
        restore.callback(stop_folder_explorers)
        toggle('windows')
        panel('w.writeConfig("launchers", ["applications:org.win7classic.explorer.desktop"]);')
        # With both named KConfig layers genuinely absent, the stock default is Remember all.
        start('Projects')
        close()
        start('Projects')
        close()
        assert json.loads(user(f'cat "{STORE}"')) == [[f'{TREE}/Projects', 2]]
        before = user(f'sha256sum "{STORE}"')
        if scenario == 'policy':
            user(f'kwriteconfig6 --file "{LOWER_POLICY}" --group {GROUP} --key what-to-remember 2')
            popup(out, 'lower-policy', 0, launcher=True)
            key('ESC')
            policy('what-to-remember', '0')
            _, x, y = popup(out, 'enabled-by-user-precedence', 1, launcher=True)
            policies = user(f'sha256sum "{CONFIG}" "{LOWER_POLICY}"')
            try:
                user(f'chmod 000 "{LOWER}"')
                assert user(f'''python - "{LOWER_POLICY}" <<'PY'
import errno, os, sys
assert os.geteuid() != 0
try:
    os.open(sys.argv[1], os.O_RDONLY)
except PermissionError as e:
    assert e.errno == errno.EACCES
    print('EACCES')
else:
    raise AssertionError('lower policy still readable')
PY''') == 'EACCES'
                reject_stale(out, 'permission-denied', x, y)
                fast_unavailable(out, 'permission-denied-reopen')
                key('ESC')
                start('Once')
                close()
                assert user(f'sha256sum "{STORE}"') == before
            finally:
                user(f'chmod {original_mode} "{LOWER}"')
            assert user(f'sha256sum "{CONFIG}" "{LOWER_POLICY}"') == policies
            popup(out, 'policy-readable-again', 1, launcher=True)
            key('ESC')
            print('optional absence, real KDE precedence, lower-directory EACCES and live dismissal verified; policy/history bytes unchanged')
        else:
            _, x, y = popup(out, 'before-invalid-store', 1, launcher=True)
            user(f'printf invalid > "{STORE}"; test -d {TREE}/Projects')
            reject_stale(out, 'invalid-store', x, y)
            assert user(f'cat "{STORE}"') == 'invalid'
            fast_unavailable(out, 'invalid-store-launch')
            key('UP'); key('UP'); key('ENTER')
            own_home_window(restore, 'Launch with unavailable history')
            fast_unavailable(out, 'invalid-store-unpin', launcher=False)
            key('UP'); key('UP'); key('ENTER')
            launchers = lambda: user('grep "^launchers=" ~/.config/plasma-org.kde.plasma.desktop-appletsrc || :')
            wait_for(lambda: 'org.win7classic.explorer.desktop' not in launchers(), 'Unpin with unavailable history')
            fast_unavailable(out, 'invalid-store-pin', launcher=False)
            key('UP'); key('UP'); key('ENTER')
            wait_for(lambda: 'org.win7classic.explorer.desktop' in launchers(), 'Pin with unavailable history')
            fast_unavailable(out, 'invalid-store-close', launcher=False)
            key('UP'); key('ENTER')
            wait_for(lambda: explorer() is None, 'Close with unavailable history')
            assert user(f'cat "{STORE}"') == 'invalid'
            print('Fast malformed-store check showed unavailable; actual Launch, Unpin, Pin and Close all worked')
            start('Once')
            close()
            assert user(f'cat "{STORE}"') == 'invalid'
            user(f'rm "{STORE}"')
            start('Projects')
            close()
            start('Projects')
            close()
            _, x, y = popup(out, 'before-deleted-store', 1, launcher=True)
            user(f'rm "{STORE}"; test -d {TREE}/Projects')
            reject_stale(out, 'deleted-store', x, y)
            assert user(f'test ! -e "{STORE}" && echo absent') == 'absent'
            start('Projects')
            close()
            start('Projects')
            close()
            popup(out, 'relearned', 1, launcher=True)
            key('DOWN')
            key('ENTER')
            wait_for(lambda: (explorer() or ('',))[0] == 'Projects', 'fresh valid Frequent row opens Explorer')
            close()
            assert json.loads(user(f'cat "{STORE}"')) == [[f'{TREE}/Projects', 3]]
            print('malformed/deleted history dismisses the stale row without launching or overwriting; real visits relearn and activate')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('scenario', choices=('policy', 'store'))
    args = parser.parse_args()
    main(args.out, args.scenario)
