"""Resource guards for live Explorer Frequent tests in the lab."""
from contextlib import ExitStack, contextmanager
import shlex
import time

from lab import toggle, user

TREE = '/home/tester/w7f35'


def current():
    if user('~/.local/bin/win7-classic status') == 'windows':
        toggle('current')


@contextmanager
def fixture(*folders):
    user(f'mkdir {TREE}')  # Never adopt a leftover or an unrelated directory.
    with ExitStack() as restore:
        # On restoration failure, retain any original that could not be moved back.
        restore.callback(user, f'if ! compgen -G "{TREE}/saved-*" >/dev/null; then rm -rf {TREE}; fi')
        user('set -e; mkdir ' + ' '.join(shlex.quote(f'{TREE}/{name}') for name in folders))
        yield restore


def stash(restore, target, name):
    saved = f'{TREE}/saved-{name}'
    absent = f'{TREE}/absent-{name}'
    restore.callback(user, f'''set -e
if test -e {saved} || test -L {saved}; then
    rm -rf "{target}"
    mv -T {saved} "{target}"
elif test -e {absent}; then
    rm -rf "{target}"
fi''')
    user(f'''set -e
if test -e "{target}" || test -L "{target}"; then mv -T "{target}" {saved}; else touch {absent}; fi''')


def unit(restore, command):
    name = f'w7f35-{time.monotonic_ns()}.service'
    restore.callback(user, f'systemctl --user kill --signal=KILL {name} 2>/dev/null || :')
    user(f'systemd-run --user --collect -q --unit={name} {command}')
    return name


def stop_folder_explorers():
    # Only invocations with an argument below the test's uniquely owned tree belong to it.
    user(f'''for proc in /proc/[0-9]*; do
    [[ $(readlink "$proc/exe" 2>/dev/null) == */win7-explorer ]] || continue
    while IFS= read -rd '' arg; do
        if [[ "$arg" == {TREE}/* ]]; then kill "${{proc##*/}}" 2>/dev/null || :; break; fi
    done < "$proc/cmdline" 2>/dev/null
 done; true''')
