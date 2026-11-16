#!/usr/bin/env python3
"""Package install/uninstall (issue #10), run from the host against the lab VM.

Builds the Arch package from this checkout inside the VM, installs it system-wide, switches to Windows mode and
back from the packaged files, then removes it: every packaged file must be gone, nothing else under /usr or /etc
may change, and the user's current-mode configuration must be byte-identical to before.
"""
import io
from pathlib import Path
import sys
import tarfile
import time

from lab import ROOT, VM, vmctl, user, toggle, close_test_apps, shot

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-package-test')
USER_STATE = ('cd ~/.config && sha256sum plasma-org.kde.plasma.desktop-appletsrc plasmashellrc kdeglobals kwinrc '
              'plasmarc kcminputrc mimeapps.list gtk-3.0/settings.ini gtk-4.0/settings.ini 2>&1; '
              'dconf read /org/gnome/desktop/interface/gtk-theme; true')
PROFILES = ('cd ~/.local/state/win7-classic/profiles && '
            'find . -printf "%y %p %l\\n" | sort; '
            'find . -type f -exec sha256sum {} + | sort')
# Caches pacman hooks refresh after any transaction (ldconfig, icon/mime/schema caches) are not ours.
SYSTEM_FILES = "find /usr /etc -xdev \\( -type f -o -type l \\) -newer /tmp/win7-pkg-marker 2>/dev/null | grep -v -e 'icon-theme.cache' -e '/usr/share/mime/' -e 'gschemas.compiled' -e 'mimeinfo.cache' -e '\\.cache-' -e '^/etc/ld.so.cache$' | sort; true"


def root(script, timeout=600):
    code, out, err = vmctl.run(VM, script, timeout)
    if code:
        raise AssertionError(f'root command failed ({code}): {script}\n{out}{err}')
    return out.strip()


def remove_user_install():
    """The per-user development install would shadow the packaged files, so it is removed for this test."""
    root('if ! pacman -Qo /usr/lib/qt6/plugins/styles/libwin7classicstyle.so >/dev/null 2>&1; then rm -f /usr/lib/qt6/plugins/styles/libwin7classicstyle.so; fi')
    user('rm -rf ~/.local/share/plasma/plasmoids/org.win7classic.* ~/.local/share/plasma/desktoptheme/win7-classic '
         '~/.local/share/kwin/decorations/win7classic ~/.local/share/themes/Win7-Classic ~/.local/share/win7-classic '
         '~/.local/share/icons/Win7-Classic ~/.local/share/icons/Win7-Classic-Cursors '
         '~/.local/share/fonts/win7-classic ~/.local/bin/win7-classic ~/.config/fontconfig/conf.d/70-win7-classic-tahoma.conf '
         '~/.local/state/win7-classic; fc-cache ~/.local/share/fonts 2>/dev/null; true')


def build_package():
    """Builds the Arch package from this checkout inside the VM; returns its path there."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name in ('install.sh', 'LICENSE', 'classic', 'explorer', 'fonts', 'packaging', 'plasma', 'toggle'):
            tar.add(ROOT / name, arcname=name, filter=lambda t: None if '__pycache__' in t.name or t.name.endswith('.pkg.tar.zst') else t)
    Path('/tmp/win7-src.tgz').write_bytes(buffer.getvalue())
    vmctl.transfer(VM, 'put', '/tmp/win7-src.tgz', '/tmp/win7-src.tgz')
    root('chmod 644 /tmp/win7-src.tgz')
    user('rm -rf /tmp/win7-build && mkdir /tmp/win7-build && tar -xzf /tmp/win7-src.tgz -C /tmp/win7-build && cd /tmp/win7-build/packaging && makepkg -f --nodeps >/tmp/makepkg.log 2>&1 || { cat /tmp/makepkg.log; exit 1; }', timeout=600)
    package = user('ls /tmp/win7-build/packaging/*.pkg.tar.zst')
    print('built', package.rsplit('/', 1)[-1])
    return package


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    close_test_apps()
    # A previous run may have left either the per-user or the packaged command in Windows mode.
    user('PATH=~/.local/bin:$PATH; command -v win7-classic >/dev/null && [ "$(win7-classic status)" = windows ] && win7-classic current; true')
    remove_user_install()
    root('pacman -Q win7-classic >/dev/null 2>&1 && pacman -Rns --noconfirm win7-classic; true')
    user('systemctl --user reset-failed plasma-plasmashell; systemctl --user restart plasma-plasmashell')
    time.sleep(4)

    root('rm -f /usr/lib/qt6/plugins/styles/libwin7classicstyle.so')
    package = build_package()

    before_user = user(USER_STATE)
    root('touch /tmp/win7-pkg-marker; sleep 1')
    root(f'pacman -U --noconfirm {package} >/tmp/pacman-install.log 2>&1 || {{ cat /tmp/pacman-install.log; exit 1; }}')
    owned = root('pacman -Qlq win7-classic | grep -v "/$" | sort').splitlines()
    print(f'installed {len(owned)} files')
    assert '/usr/share/icons/Win7-Classic-Cursors/cursors/default' in owned, 'cursor theme not packaged'
    assert root('readlink /usr/share/icons/Win7-Classic-Cursors/cursors/xterm') == 'text'
    assert '/usr/lib/qt6/plugins/styles/libwin7classicstyle.so' in owned
    assert '/usr/share/win7-classic/primitives/libwin7classicqml.so' in owned
    assert '/usr/bin/win7-classic-probe' in owned
    assert '/usr/bin/win7-classic' in owned and root('readlink -f /usr/bin/win7-classic') == '/usr/share/win7-classic/win7-classic'
    assert root('test -L /etc/fonts/conf.d/70-win7-classic-tahoma.conf && echo linked') == 'linked', 'fontconfig rule not enabled'
    assert root('fc-match -f "%{file}" Tahoma') == '/usr/share/fonts/win7-classic/tahoma.ttf'

    root('mv /usr/lib/qt6/plugins/styles/libwin7classicstyle.so /tmp/win7-style-held.so')
    try:
        code, _, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- win7-classic windows', 180)
        assert code != 0 and 'cd packaging && makepkg -si' in err, err
        assert user(USER_STATE) == before_user, 'missing-style refusal changed configuration'
        code, _, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- /tmp/win7-build/install.sh', 180)
        assert code != 0 and 'cd packaging && makepkg -si' in err, err
    finally:
        root('mv /tmp/win7-style-held.so /usr/lib/qt6/plugins/styles/libwin7classicstyle.so')
    print('missing-style install/switch both fail before changing configuration')
    code, _, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- win7-classic windows', 180)
    assert code == 0, err
    time.sleep(2)
    # Both profiles must exist: a refusal must preserve the saved Windows layout, not just live settings.
    user('win7-classic current')
    failures = []
    for mode in ('current', 'windows'):
        user(f'win7-classic windows && win7-classic current && win7-classic {mode}')
        root('mv /usr/lib/qt6/plugins/styles/libwin7classicstyle.so /tmp/win7-style-held.so')
        try:
            for command in ('windows', 'rebuild'):
                config_before, profiles_before = user(USER_STATE), user(PROFILES)
                code, _, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- win7-classic {command}', 180)
                checks = {
                    'nonzero exit and repair guidance': code != 0 and 'cd packaging && makepkg -si' in err,
                    'unchanged mode': user('win7-classic status') == mode,
                    'byte-identical configuration': user(USER_STATE) == config_before,
                    'unchanged saved profiles': user(PROFILES) == profiles_before,
                }
                for check, passed in checks.items():
                    print(f'missing-style {command} from {mode}: {check}: {"PASS" if passed else "FAIL"}')
                    if not passed:
                        failures.append(f'{command} from {mode}: {check}')
        finally:
            root('mv /tmp/win7-style-held.so /usr/lib/qt6/plugins/styles/libwin7classicstyle.so')
    assert not failures, '\n'.join(failures)
    print('missing-style windows/rebuild refuse from both modes without changing configuration or saved profiles')
    shot(OUT / '1-windows-from-package.png')
    assert user('kreadconfig6 --file kcminputrc --group Mouse --key cursorTheme') == 'Win7-Classic-Cursors'
    assert user('gsettings get org.gnome.desktop.interface cursor-theme') == "'Win7-Classic-Cursors'"
    widgets = user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "print(panels()[0].widgets().map(w => w.type).join(\\" \\"))"')
    assert 'org.win7classic.taskbar' in widgets and 'org.win7classic.clock' in widgets, widgets
    assert 'win7classic' in user('qdbus6 org.kde.KWin /KWin supportInformation | grep -A3 ^Decoration'), 'packaged decoration not loaded'
    code, _, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- win7-classic current', 180)
    assert code == 0, err
    time.sleep(2)
    print('switched to Windows mode and back using only the packaged files')

    root('pacman -R --noconfirm win7-classic >/tmp/pacman-remove.log 2>&1 || { cat /tmp/pacman-remove.log; exit 1; }')
    leftovers = [f for f in owned if root(f'test -e {f} -o -L {f} && echo yes || echo no') == 'yes']
    assert not leftovers, f'files left after removal: {leftovers}'
    changed = root(SYSTEM_FILES).splitlines()
    assert not changed, f'files under /usr or /etc changed by install+remove: {changed}'
    after_user = user(USER_STATE)
    print(before_user)
    print(after_user)
    assert after_user == before_user, f'current-mode configuration changed:\n{before_user}\n---\n{after_user}'
    user('systemctl --user reset-failed plasma-plasmashell; systemctl --user restart plasma-plasmashell')
    time.sleep(4)
    shot(OUT / '2-after-uninstall.png')
    print('package removed cleanly; current mode untouched')

    # Removing while still in Windows mode must at least warn; the user's saved layout stays recoverable.
    root(f'pacman -U --noconfirm {package} >/dev/null 2>&1')
    vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- win7-classic windows', 180)
    warning = root('pacman -R --noconfirm win7-classic 2>&1')
    assert 'tester is still in Windows 7 Classic mode' in warning, warning
    assert user('test -f ~/.local/state/win7-classic/profiles/current/plasma-org.kde.plasma.desktop-appletsrc && echo kept') == 'kept'
    # Recovery path: reinstall, switch back, remove again.
    root(f'pacman -U --noconfirm {package} >/dev/null 2>&1')
    code, _, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- win7-classic current', 180)
    assert code == 0, err
    root('pacman -R --noconfirm win7-classic >/dev/null 2>&1')
    assert user(USER_STATE) == before_user, 'reinstall + switch back did not recover the current layout'
    print('removing while in Windows mode warns; reinstalling and switching back recovers the layout exactly')
    print('ALL PACKAGE CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
