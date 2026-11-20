#!/usr/bin/env python3
"""Windows activation must roll back when the enabled packaged volume UI cannot load."""
import argparse
from pathlib import Path

from lab import VM, digest, shot, toggle, user, vmctl

VOLUME = '/usr/share/plasma/plasmoids/org.win7classic.volume'
LAYOUT = 'plasma-org.kde.plasma.desktop-appletsrc'
PROFILE = '~/.local/state/win7-classic/profiles/windows'
STATUS = '/usr/bin/win7-classic status'
PANEL = """qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript 'var types = []; for (const p of panels()) for (const w of p.widgets()) types.push(w.type); print(types.join(","))'"""


def root(script):
    code, stdout, stderr = vmctl.run(VM, 'set -e\n' + script, 30)
    assert code == 0, stdout + stderr


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    assert user(STATUS) == 'current'
    print(toggle('windows', packaged=True), end='')
    assert 'plugin=org.win7classic.volume' in user(f'cat ~/.config/{LAYOUT}').splitlines(), 'start with stock Volume enabled'
    print(toggle('current', packaged=True), end='')
    before = digest()
    stock = user(PANEL)
    assert 'org.kde.plasma.systemtray' in stock, stock
    kwin = user('pgrep -x kwin_wayland')
    saved = user(f'cd {PROFILE}; sha256sum *')

    # Hide the installed UI package, then prove a broken QML file also fails even with valid metadata.
    for failure in ('missing', 'unloadable'):
        path = VOLUME if failure == 'missing' else f'{VOLUME}/contents/ui/main.qml'
        backup = f'{path}.w7-readiness-test'
        root(f'test ! -e {backup}; mv {path} {backup}')
        try:
            if failure == 'unloadable':
                root(f'printf "import Win7ReadinessTestNonexistent\\nItem {{}}\\n" > {path}')
            code, stdout, stderr = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- /usr/bin/win7-classic windows', 180)
            (out / f'{failure}.log').write_text(f'exit={code}\n{stdout}{stderr}')
            print(f'{failure}: exit={code}\n{stderr}', end='')
            assert code != 0 and 'Classic volume frontend' in stderr and 'rolling back to current' in stderr, stderr
            assert user(STATUS) == 'current' and digest() == before and user(PANEL) == stock
            assert user('pgrep -x kwin_wayland') == kwin
            assert user(f'cd {PROFILE}; sha256sum *') == saved
            shot(out / f'{failure}-stock.png')
        finally:
            root(f'mv -T {backup} {path}')
            if user(STATUS) == 'windows':
                toggle('current', packaged=True)

    config = f'{PROFILE}/{LAYOUT}'
    backup = f'{PROFILE}/../volume-readiness-test-appletsrc'
    user(f'test ! -e {backup} && cp -p {config} {backup}')
    try:
        user(f"sed -i '/^extraItems=/s/,org\\.kde\\.plasma\\.volume//g' {config}")
        assert not any('org.kde.plasma.volume' in line for line in user(f'grep ^extraItems= {config}').splitlines())
        root(f'test ! -e {VOLUME}.w7-readiness-test; mv {VOLUME} {VOLUME}.w7-readiness-test')
        try:
            print(toggle('windows', packaged=True), end='')
            assert user(STATUS) == 'windows', 'disabled Volume must not block activation'
            shot(out / 'disabled-windows.png')
        finally:
            root(f'mv -T {VOLUME}.w7-readiness-test {VOLUME}')
    finally:
        if user(STATUS) == 'windows':
            toggle('current', packaged=True)
        user(f'mv -T {backup} {config}')
    assert digest() == before and user(PANEL) == stock and user('pgrep -x kwin_wayland') == kwin
    assert user(f'cd {PROFILE}; sha256sum *') == saved
    print('Missing and unloadable enabled frontend refused; disabled Volume stayed optional; exact layout and stock panel restored.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    main(parser.parse_args().out)
