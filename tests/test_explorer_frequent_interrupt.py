#!/usr/bin/env python3
"""Crash before the final authorization; replay real Back/Forward while policy I/O is held."""
import argparse
import json
from pathlib import Path
import tempfile
import time

from explorer_frequent_fixture import TREE, fixture, stash, unit
from lab import ROOT, VM, kwin_query, shot, toggle, user, vmctl, wait_for
from test_explorer_frequent import APP, STATE, explorer, go, key
from test_explorer_frequent_privacy import CONFIG, policy


def test(out, scenario):
    with fixture('Alpha', 'Bravo', 'Charlie', 'Delta', 'Denied') as restore:
        restore.callback(user, 'systemctl --user restart plasma-kactivitymanagerd')
        stash(restore, CONFIG, 'policy')
        stash(restore, STATE, 'history')
        restore.callback(toggle, 'current', packaged=True)
        policy('what-to-remember', '0')
        policy('off-the-record-activities', '')
        toggle('windows', packaged=True)
        # Compile only the test shim; Explorer and the policy helper remain the installed package.
        with tempfile.TemporaryDirectory() as scratch:
            src = Path(scratch) / 'interrupt.c'
            src.write_bytes((ROOT / 'tests/explorer-frequent/interrupt.c').read_bytes())
            vmctl.transfer(VM, 'put', str(src), f'{TREE}/interrupt.c')
        user(f'cc -Wall -Wextra -Werror -shared -fPIC -o {TREE}/interrupt.so {TREE}/interrupt.c -ldl')
        mark = f'{TREE}/held'
        arm = f'{TREE}/hold'
        env = f'LD_PRELOAD={TREE}/interrupt.so W7_TEST_MARKER={mark}'
        if scenario == 'kill':
            env += f' W7_TEST_STOP_IN="{STATE}"'
        else:
            env += f' W7_TEST_HOLD_POLICY="{CONFIG}" W7_TEST_HOLD_ARM={arm}'
        service = unit(restore, f'/usr/bin/env {env} /usr/bin/win7-explorer')
        restore.callback(user, f'rm -f {arm}')
        wait_for(lambda: (explorer() or ('',))[0] == 'tester', 'installed Explorer ready')
        pid = user(f'systemctl --user show -p MainPID --value {service}')
        assert pid.isdigit() and int(pid) > 0 and user(f'readlink /proc/{pid}/exe') == '/usr/bin/win7-explorer'
        if scenario == 'kill':
            go('Denied')
            wait_for(lambda: user(f'test -s {mark} && grep "^State:.*stopped" /proc/{pid}/status', check=False),
                     'real stage fsync complete and process stopped before authorization')
            # Activity policy is denied before terminating the writer without any application cleanup.
            policy('what-to-remember', '2')
            assert user(f'kreadconfig6 --file "{CONFIG}" --group Plugin-org.kde.ActivityManager.Resources.Scoring --key what-to-remember') == '2'
            before = user(f'find "{STATE}" -mindepth 1 -maxdepth 1 -printf "%f\\n"')
            user(f'kill -KILL {pid}')
            wait_for(lambda: explorer() is None, 'SIGKILL removed the window')
            wait_for(lambda: user(f'test ! -d /proc/{pid} && echo gone', check=False) == 'gone', 'writer reaped')
            after = user(f'find "{STATE}" -mindepth 1 -maxdepth 1 -printf "%f\\n"')
            shot(out / 'killed-before-authorization.png')
            print(f'fsync completed before final check; denied then SIGKILL. Entries while held: {before!r}, after death: {after!r}')
            if after:
                print(user(f'grep -lF "{TREE}/Denied" "{STATE}"/.* 2>/dev/null', check=False))
            assert not before and not after, 'unapproved history had a name and survived SIGKILL'
            return

        for folder in ('Alpha', 'Bravo', 'Charlie', 'Delta'):
            go(folder)
        [xy] = kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass === "{APP}" && w.active) '
                          'emit(w.clientGeometry.x, w.clientGeometry.y);')
        assert user('kscreen-doctor -j | jq -c "[.outputs[] | select(.enabled) | .scale]"') == '[1]'
        x, y = map(int, xy)
        failures = []
        for direction, offset, start, expected in (('Back', 16, 'Delta', 'Bravo'), ('Forward', 45, 'Bravo', 'Delta')):
            assert explorer()[0] == start
            vmctl.pointer(VM, x + offset, y + 17)
            user(f'rm -f {mark}; touch {arm}')
            # vmctl.pointer's normal per-event delay would let the first 180 ms deadline expire.
            for down in (True, False, True, False):
                vmctl.virsh('qemu-monitor-command', VM, json.dumps({'execute': 'input-send-event', 'arguments': {
                    'events': [{'type': 'btn', 'data': {'button': 'left', 'down': down}}]}}))
                time.sleep(0.012)
            wait_for(lambda: user(f'test -s {mark} && wc -l < {mark}', check=False) == '2',
                     'both real clicks began policy preflight while the first remained held')
            wait_for(lambda: (explorer() or ('',))[0] != start, 'bounded preflight released navigation')
            actual = explorer()[0]
            shot(out / f'two-{direction.lower()}-while-held.png')
            assert user(f'test -e {arm} && wc -l < {mark}') == '2'
            print(f'two real {direction} clicks while both preflights were held: {actual}; expected {expected}')
            user(f'rm {arm}')
            # Do not start the next case until the first workers have drained their real policy I/O.
            wait_for(lambda: not user(f'grep -l "hrtimer_nanosleep" /proc/{pid}/task/*/wchan', check=False),
                     'both held workers returned')
            if actual != expected:
                failures.append((direction, actual, expected))
                if direction == 'Back':
                    assert actual == 'Charlie', actual
                    key('LEFTALT', 'LEFT')
                    wait_for(lambda: (explorer() or ('',))[0] == 'Bravo', 'single Back positions the independent Forward case')
        assert not failures, failures
        key('LEFTCTRL', 'W')
        wait_for(lambda: explorer() is None, 'fixture Explorer closed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('scenario', choices=['kill', 'history'])
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    test(args.out, args.scenario)
