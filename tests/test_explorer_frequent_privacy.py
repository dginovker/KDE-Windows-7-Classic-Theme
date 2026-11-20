#!/usr/bin/env python3
"""Drive Explorer and the Classic taskbar against Plasma's effective Recent Files policy."""
import json
from pathlib import Path
import shlex
import sys
import time

from PIL import Image

from lab import VM, kwin_query, shot, toggle, user, vmctl, wait_for
from test_explorer_frequent import APP, BLACK, PROFILE, STATE, explorer, go, key, panel, popup
from explorer_frequent_fixture import TREE, current, fixture, stash, stop_folder_explorers, unit

CONFIG = '${XDG_CONFIG_HOME:-$HOME/.config}/kactivitymanagerd-pluginsrc'
GROUP = 'Plugin-org.kde.ActivityManager.Resources.Scoring'
STORE = f'{STATE}/frequent.json'
EXE = '$HOME/.local/bin/win7-explorer'


def policy(key, value, extra=''):
    user(f'kwriteconfig6 --notify --file "{CONFIG}" --group {GROUP} --key {key} {extra} {shlex.quote(value)}')


def start(name, expect_caption=True):
    user(f'systemd-run --user --collect -q {EXE} {TREE}/{name}')
    if expect_caption:
        wait_for(lambda: (explorer() or ('',))[0] == name, f'Explorer opened {name}')


def close():
    key('LEFTCTRL', 'W')
    wait_for(lambda: explorer() is None, 'Explorer closed')


def saved_current():
    return user('find "${XDG_STATE_HOME:-$HOME/.local/state}/win7-classic/profiles/current" -type f -print0 | '
                'sort -z | xargs -0r sha256sum')


def root(script):
    code, out, err = vmctl.run(VM, script, 20)
    assert code == 0, out + err


def recent():
    return user('cd "${XDG_DATA_HOME:-$HOME/.local/share}"; '
                'if test -d RecentDocuments; then find RecentDocuments -type f -print0 | sort -z | xargs -0r sha256sum; fi; '
                'if test -f recently-used.xbel; then sha256sum recently-used.xbel; fi')


def immediate_rmdir_click(x, y):
    vmctl.pointer(VM, x, y)
    proc = vmctl.agent(VM, 'guest-exec', {'path': '/usr/bin/runuser',
        'arg': ['-u', 'tester', '--', 'rmdir', f'{TREE}/Projects'], 'capture-output': True})['pid']
    deadline = time.monotonic() + 2
    while True:
        state = vmctl.agent(VM, 'guest-exec-status', {'pid': proc})
        if state.get('exited'):
            assert state.get('exitcode') == 0, state
            break
        assert time.monotonic() < deadline
    for down in (True, False):
        vmctl.virsh('qemu-monitor-command', VM, json.dumps({
            'execute': 'input-send-event', 'arguments': {
                'events': [{ 'type': 'btn', 'data': {'button': 'left', 'down': down}}]}}))


def visible_error(shell_pid):
    return ['Windows Explorer', shell_pid, 'true'] in kwin_query(
        'for (const w of workspace.windowList()) emit(w.caption, w.pid, w.active);')


def dismissed(out, name, x, y):
    path = out / f'{name}.png'
    shot(path)
    with Image.open(path) as image:
        return image.convert('RGB').getpixel((x + 100, y)) != BLACK


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    assert user('~/.local/bin/win7-classic status') == 'current'
    assert explorer() is None, 'the Explorer task button must belong to the test'
    desktop = '${XDG_DATA_HOME:-$HOME/.local/share}/applications/org.win7classic.explorer.desktop'
    recover_exe = f'if test -e {TREE}/saved-exe; then mv {TREE}/saved-exe "{EXE}"; fi'
    with fixture('Once', 'Projects', 'Outside') as restore:
        restore.callback(user, 'systemctl --user restart plasma-kactivitymanagerd')
        stash(restore, STATE, 'history')
        stash(restore, PROFILE, 'profile')
        stash(restore, CONFIG, 'policy')
        user(f'set -e; cp -a "{desktop}" {TREE}/desktop-copy; mv {TREE}/desktop-copy {TREE}/saved-desktop')
        restore.callback(user, f'set -e; mv {TREE}/saved-desktop "{desktop}"; kbuildsycoca6')
        restore.callback(current)
        restore.callback(stop_folder_explorers)
        restore.callback(user, recover_exe)
        policy('what-to-remember', '0')
        start('Projects')
        go('Once')
        close()
        assert user(f'test ! -e "{STATE}" && echo absent') == 'absent'
        toggle('windows')
        panel('w.writeConfig("launchers", ["applications:org.win7classic.explorer.desktop"]);')
        first = saved_current()
        state_path = shlex.quote(user(f'printf "%s" "{STATE}"'))
        policy('what-to-remember', '2')
        start('Projects')
        close()
        popup(out, 'do-not-remember', 0, launcher=True)
        key('ESC')
        assert user(f'test ! -e "{STATE}" && echo absent') == 'absent'
        policy('what-to-remember', '0')
        start('Projects')
        close()
        start('Projects')
        close()
        initial = user(f'cat "{STORE}"')
        assert json.loads(initial) == [[f'{TREE}/Projects', 2]]
        assert user(f'stat -c %a "{STATE}" "{STORE}"') == '700\n600'

        # Exclude Explorer in Plasma's Specific Applications list while its real popup is open.
        _, x, y = popup(out, 'before-live-exclusion', 1, launcher=True)
        policy('blocked-applications', APP)
        policy('what-to-remember', '1')
        key('DOWN')
        key('ENTER')
        time.sleep(.5)
        shot(out / 'after-live-exclusion.png')
        image = Image.open(out / 'after-live-exclusion.png').convert('RGB')
        assert image.getpixel((x + 100, y)) != (0, 0, 0), 'stale Frequent popup still showing'
        assert explorer() is None, 'stale excluded row opened Explorer'
        assert user(f'cat "{STORE}"') == initial
        popup(out, 'exclude-explorer', 0, launcher=True)
        key('ESC')
        start('Once')
        close()
        assert user(f'cat "{STORE}"') == initial
        policy('what-to-remember', 'not-a-mode')
        popup(out, 'invalid-policy', 0, launcher=True, unavailable=True)
        key('ESC')
        start('Once')
        close()
        assert user(f'cat "{STORE}"') == initial
        policy('what-to-remember', '1')
        policy('blocked-by-default', 'true', '--type bool')
        popup(out, 'allowlist-empty', 0, launcher=True)
        key('ESC')
        policy('allowed-applications', APP)
        popup(out, 'allowlist-explorer', 1, launcher=True)
        key('ESC')
        print('current/global disable, live Explorer exclusion, allowlist and invalid policy: hide and do not write; existing bytes preserved')

        policy('what-to-remember', '0')
        policy('url-filters', f'{TREE}/Pro*')
        popup(out, 'url-excluded', 0, launcher=True)
        key('ESC')
        start('Projects')
        close()
        assert user(f'cat "{STORE}"') == initial
        policy('url-filters', 'about:*,*/.*,/,/tmp/*')
        activity = user('qdbus6 org.kde.ActivityManager /ActivityManager/Activities '
                        'org.kde.ActivityManager.Activities.CurrentActivity')
        assert activity
        policy('off-the-record-activities', activity)
        popup(out, 'private-activity', 0, launcher=True)
        key('ESC')
        start('Projects')
        close()
        assert user(f'cat "{STORE}"') == initial
        policy('off-the-record-activities', '')
        print('KDE URL exclusion and current private activity: hide and do not write')
        # Simultaneous real launchings all merge their counts, with no seed/instrumentation in the product.
        script = f'for i in {{1..6}}; do {EXE} {TREE}/Projects & done; wait'
        writers = unit(restore, 'bash -c ' + shlex.quote(script))
        wait_for(lambda: json.loads(user(f'cat "{STORE}"')) == [[f'{TREE}/Projects', 8]], 'six concurrent Explorer visits merged')
        user(f'systemctl --user stop {writers}')
        wait_for(lambda: explorer() is None, 'six test windows closed')
        before = user(f'sha256sum "{STORE}"')
        root(f'mount --bind {state_path} {state_path}')
        try:
            root(f'mount -o remount,bind,ro {state_path}')
            reader_unit = f'w7f35-ro-{time.monotonic_ns()}'
            user(f'systemd-run --user --collect -q --unit={reader_unit} {EXE} {TREE}/Projects')
            wait_for(lambda: (explorer() or ('',))[0] == 'Projects', 'Explorer opened a folder with read-only history')
            wait_for(lambda: 'cannot create Frequent history staging file (Read-only file system)' in user(f'journalctl --user -u {reader_unit} --no-pager -o cat'),
                     'read-only fixture mount produces a Frequent save error')
            assert user(f'sha256sum "{STORE}"') == before
            close()
        finally:
            root(f'umount {state_path}')
        for label, setup, verify in (
            ('malformed', f'printf invalid > "{STORE}"; chmod 600 "{STORE}"', f'test "$(cat "{STORE}")" = invalid'),
            ('oversized', f'truncate -s 1048577 "{STORE}"; chmod 600 "{STORE}"', f'test "$(stat -c %s "{STORE}")" = 1048577'),
            ('fifo', f'mkfifo -m 600 "{STORE}"', f'test -p "{STORE}"'),
            ('symlink', f'ln -s {TREE}/sentinel "{STORE}"', f'test -L "{STORE}"; test "$(cat {TREE}/sentinel)" = pristine'),
        ):
            user(f'set -e; mv "{STORE}" {TREE}/good; printf pristine > {TREE}/sentinel; {setup}')
            popup(out, label, 0, launcher=True, unavailable=True)
            key('ESC')
            start('Once')
            close()
            user(f'set -e; {verify}; rm "{STORE}"; mv {TREE}/good "{STORE}"')
        user(f'chmod 0755 "{STATE}"')
        popup(out, 'insecure-directory', 0, launcher=True, unavailable=True)
        key('ESC')
        start('Once')
        close()
        assert user(f'sha256sum "{STORE}"') == before
        user(f'chmod 0700 "{STATE}"')
        print('six concurrent writers, failed atomic save, malformed/large/symlink/FIFO store and loose directory permissions verified')

        shell_pid = user('systemctl --user show plasma-plasmashell -p MainPID --value')
        assert shell_pid.isdigit() and int(shell_pid) > 0
        error = lambda: visible_error(shell_pid)

        # Replacement, not deletion: a regular file still has the same canonical path.
        _, x, y = popup(out, 'before-folder-replaced', 1, launcher=True)
        user(f'rmdir {TREE}/Projects; touch {TREE}/Projects')
        wait_for(lambda: dismissed(out, 'folder-replaced-dismissed', x, y),
                 'poll dismissed a destination replaced by a regular file', timeout=3)
        vmctl.pointer(VM, x + 85, y + 43, 'left')
        assert not error() and explorer() is None, 'click after dismissal did not stay inert'
        assert user(f'sha256sum "{STORE}"') == before
        user(f'rm {TREE}/Projects; mkdir {TREE}/Projects')

        # Also drive the true click-before-poll race. Both outcomes forbid opening any Explorer.
        for i in range(12):
            _, x, y = popup(out, f'before-folder-removed-{i}', 1, launcher=True)
            time.sleep((i % 8) * .027)
            immediate_rmdir_click(x + 85, y + 43)
            assert explorer() is None, 'removed destination opened Explorer'
            if error():
                shot(out / 'folder-removed-error.png')
                key('ESC')
                user(f'mkdir {TREE}/Projects')
                break
            assert dismissed(out, f'folder-removed-dismissed-{i}', x, y)
            user(f'mkdir {TREE}/Projects')
        else:
            raise AssertionError('never exercised a real stale click before polling dismissed the menu')
        _, x, y = popup(out, 'before-missing-explorer', 1, launcher=True)
        user(f'mv "{EXE}" {TREE}/saved-exe')
        vmctl.pointer(VM, x + 85, y + 43, 'left')
        wait_for(error, 'visible error from the actual plasmashell for missing installed Explorer')
        shot(out / 'missing-explorer-error.png')
        assert explorer() is None
        key('ESC')
        user(recover_exe)
        # Override the desktop service without changing the installed binary. A Frequent row must not resolve it.
        user(f'sed -i "s|^Exec=.*|Exec=/usr/bin/touch {TREE}/wrong-app %U|" "{desktop}"; kbuildsycoca6')
        snapshot = recent()
        popup(out, 'desktop-override', 1, launcher=True)
        key('DOWN')
        key('ENTER')
        wait_for(lambda: (explorer() or ('',))[0] == 'Projects', 'known Explorer executable opened the folder')
        close()
        assert user(f'test ! -e {TREE}/wrong-app && echo absent') == 'absent'
        assert recent() == snapshot, 'Frequent activation changed shared RecentDocuments/recently-used.xbel'
        print('regular-file replacement dismissed, removed-folder/installed-executable errors reported visibly; desktop override ignored; both shared recent stores unchanged')
        toggle('current')
        assert first == saved_current(), 'saved current profile files changed'
        print('saved current profile file hashes unchanged')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
