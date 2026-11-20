#!/usr/bin/env python3
"""Inject silent migration/seed errors in the installed guest copy, never the host."""
from pathlib import Path
import shlex
import sys
import time

from PIL import Image
from lab import VM, digest, shot, toggle, user, vmctl, wait_for

ROOT = '/tmp/w39-switch-test'
SHARE = ROOT + '/share/win7-classic'
PROFILES = '~/.local/state/win7-classic/profiles'
APPLETS = 'plasma-org.kde.plasma.desktop-appletsrc'
TRAY = SHARE + '/windows/migrate-tray'
SEED = SHARE + '/windows/seed'
TRACE = '/tmp/w39-appearance-trace'
STAGED = '/tmp/w39-failed-layout'
BIN = '/tmp/w39-switch-bin'


def profile(name):
    return user(f'cd {PROFILES}/{name} && find . -type f -print0 | sort -z | xargs -0 sha256sum')


def write(path, text):
    user(f'printf %s {shlex.quote(text)} >{path}')


def main(out, switch_edges=False):
    out.mkdir(parents=True, exist_ok=True)
    assert user('/usr/bin/win7-classic status') == 'current'
    toggle('windows', packaged=True)
    toggle('current', packaged=True)
    # Reverse only the tray substitution to exercise the supported packaged upgrade input.
    user(f"/usr/share/win7-classic/windows/migrate-tray --undo {PROFILES}/windows/{APPLETS}")
    windows = profile('windows')
    script = SHARE + '/win7-classic'
    user(f"mkdir -p {ROOT}/share {ROOT}/bin; cp -a /usr/share/win7-classic {SHARE}; "
         f"ln -s /usr/bin/win7-classic-probe {ROOT}/bin/; cp {TRAY} {TRAY}.real; cp {SEED} {SEED}.real; "
         f"sed -i '/^load_appearance() {{/a\\    printf \"%s\\\\n\" \"$1\" >>{TRACE}' {script}")

    def run():
        return vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- env PATH={BIN}:/usr/bin {script} toggle', 180)

    def reject(name, status, diagnostic, appearance='current'):
        before = digest()
        theme = user('kreadconfig6 --file kdeglobals --group Icons --key Theme')
        user(f'rm -f {TRACE} {STAGED}')
        code, stdout, stderr = run()
        (out / f'{name}.log').write_text(f'exit={code}\n{stdout}{stderr}')
        assert code == status and diagnostic in stderr and 'rolling back to current' in stderr, stderr
        assert user(f'cat {TRACE}') == appearance, 'incorrect appearance sequence'
        assert user('kreadconfig6 --file kdeglobals --group Icons --key Theme') == theme, 'current icon theme not restored'
        assert digest() == before, f'{name}: live layout changed'
        saved_current = user(f'cd {PROFILES}/current; sha256sum {APPLETS} plasmashellrc plasmarc 2>&1 || true')
        assert saved_current == before, f'{name}: current profile differs from the sampled live layout'
        assert user('/usr/bin/win7-classic status') == 'current'
        assert user('systemctl --user is-active plasma-plasmashell') == 'active'
        assert 'org.kde.plasma.kickoff' in user("qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript 'print(panels()[0].widgets().map(w=>w.type).join(\",\"))'")
        vmctl.pointer(VM, 640, 400)
        time.sleep(0.5)
        baseline = out / f'{name}-stock.png'
        shot(baseline)
        box = (0, 350, 330, 735)
        vmctl.keys(VM, 'KEY_LEFTMETA')
        menu = out / f'{name}-launcher.png'

        def launcher_open():
            shot(menu)
            with Image.open(menu) as opened, Image.open(baseline) as closed:
                return opened.crop(box) != closed.crop(box)

        wait_for(launcher_open, 'real stock kickoff opens after rollback')
        vmctl.keys(VM, 'KEY_ESC')
        time.sleep(1)  # The menu sets stock KConfig metadata; sample after it has been saved.
        print(f'{name}: exit {code}; appearance sequence {appearance.splitlines()}; exact current config and working launcher')

    def ordinary_switch_errors():
        user(f'mkdir {BIN}')
        # Fail after the first real copy so rollback has to undo a partial layout replacement.
        write(BIN + '/cp', '#!/bin/bash\n'
              'if [[ $2 == */windows/plasmashellrc ]]; then\n'
              f'    cmp -s "$HOME/.config/{APPLETS}" "${{2%/*}}/{APPLETS}" || exit 90\n'
              '    echo lab-refused-second-file >&2\n    exit 45\nfi\nexec /usr/bin/cp "$@"\n')
        user(f'chmod +x {BIN}/cp')
        reject('target-copy', 45, 'copying saved windows layout failed (exit 45): lab-refused-second-file')
        assert profile('windows') == windows
        user(f'rm {BIN}/cp')
        write(BIN + '/qdbus6', '#!/bin/bash\n'
              'if [[ $4 == "var bad = "* ]]; then\n'
              "    /usr/bin/qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript 'print(panels()[0].widgets().map(w=>w.type).join(\",\"))' "
              '| grep -q org.win7classic.taskbar || exit 91\n'
              f'    if [[ -e {BIN}/warn ]]; then\n'
              '        widgets=$(/usr/bin/qdbus6 "$@") || exit "$?"\n'
              '        [[ -z $widgets ]] || exit 92\n'
              '        echo lab-widget-query-warning >&2\n        exit 0\n    fi\n'
              '    echo lab-refused-widget-query >&2\n    exit 46\nfi\nexec /usr/bin/qdbus6 "$@"\n')
        user(f'chmod +x {BIN}/qdbus6')
        reject('widget-query', 46, 'querying windows panel widgets failed (exit 46)', 'windows\ncurrent')
        assert 'lab-refused-widget-query' in (out / 'widget-query.log').read_text()
        assert profile('windows') == windows
        user(f'touch {BIN}/warn')
        before = digest()
        code, stdout, stderr = run()
        (out / 'widget-query-warning.log').write_text(f'exit={code}\n{stdout}{stderr}')
        assert code == 0 and 'lab-widget-query-warning' in stderr, stderr
        assert user('/usr/bin/win7-classic status') == 'windows'
        assert user('kreadconfig6 --file kdeglobals --group Icons --key Theme') == 'Win7-Classic'
        shot(out / 'widget-query-warning.png')
        user(f'rm {BIN}/qdbus6 {BIN}/warn')
        toggle('current', packaged=True)
        assert digest() == before
        print('successful empty widget query with stderr warning still activated Windows; exact current restored')
        before = digest()
        for mode in ('windows', 'current'):
            code, stdout, stderr = run()
            (out / f'toggle-{mode}.log').write_text(f'exit={code}\n{stdout}{stderr}')
            assert code == 0 and user('/usr/bin/win7-classic status') == mode, stderr
            assert user('systemctl --user is-active plasma-plasmashell') == 'active'
            shot(out / f'toggle-{mode}.png')
        assert digest() == before
        print('both failures left saved Windows input exact; ordinary toggle succeeds in both directions')

    try:
        if switch_edges:
            ordinary_switch_errors()
            return
        write(TRAY, '#!/bin/bash\n[[ $1 != --check ]] || exec "$0.real" "$@"\nexit 42\n')
        reject('silent', 42, 'System Tray migration failed (exit 42)')
        assert profile('windows') == windows and not user(f'test -e {STAGED} && echo mutated', check=False)
        print('silent: real read-only check passed; exact saved Windows input')
        write(TRAY, '#!/bin/bash\nset -e\n[[ $1 != --check ]] || exec "$0.real" "$@"\n'
              f'"$0.real" "$@" >/dev/null\ncp "$1" {STAGED}\nexit 43\n')
        reject('post-replace', 43, 'System Tray migration failed (exit 43)')
        assert profile('windows') == windows
        user(f"grep -x plugin=org.win7classic.tray {STAGED}; "
             f"{TRAY}.real --undo {STAGED}; cmp {STAGED} {PROFILES}/windows/{APPLETS}")
        print('post-replace: real migration modified only the tray plugin in staged bytes; exact saved Windows input')

        user(f'cp {TRAY}.real {TRAY}; mv {PROFILES}/windows {PROFILES}/w39-saved-windows')
        write(SEED, '#!/bin/bash\nset -e\n"$0.real" "$@" >/dev/null\n'
              f'cp "$1/{APPLETS}" {STAGED}\nexit 44\n')
        reject('first-seed', 44, 'seeding windows failed (exit 44)')
        assert not user(f'test -e {PROFILES}/windows && echo created', check=False)
        assert profile('w39-saved-windows') == windows
        assert user(f'grep -x plugin=org.win7classic.taskbar {STAGED}') == 'plugin=org.win7classic.taskbar'
        print('first-seed: real seed replaced staged layout, no Windows profile was created')
    finally:
        user(
             f'if [[ -d {PROFILES}/w39-saved-windows ]]; then mv {PROFILES}/w39-saved-windows {PROFILES}/windows; fi; '
             f'rm -f {TRACE} {STAGED}; rm -rf {BIN} {ROOT}')


if __name__ == '__main__':
    main(Path(sys.argv[1]), switch_edges=sys.argv[2:] == ['--switch-edges'])
