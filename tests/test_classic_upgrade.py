#!/usr/bin/env python3
"""Old native QML registrations survive package/development upgrades without a KWin restart (#17)."""
from pathlib import Path
import subprocess
import sys
import time
from lab import ROOT, VM, vmctl, user, shot, wait_for, assert_portal_display, close_test_apps
from test_package import build_package, root, remove_user_install
from test_login import restart_sddm, logged_in
import test_frames as frames

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-classic-upgrade-test')
OLD = '1e7b2f7'
UNVERSIONED = '04fff9f'
CLI = '/usr/bin/win7-classic'


def mode(target, expect_ok=True):
    code, out, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- {CLI} {target}', 240)
    assert (code == 0) == expect_ok, (target, code, out, err)
    return out + err


def development_install(commit=None):
    global CLI
    archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', '--format=tar.gz', commit]) if commit else Path('/tmp/win7-src.tgz').read_bytes()
    Path('/tmp/win7-upgrade.tgz').write_bytes(archive)
    vmctl.transfer(VM, 'put', '/tmp/win7-upgrade.tgz', '/tmp/win7-upgrade.tgz')
    root('chmod 644 /tmp/win7-upgrade.tgz')
    user('rm -rf /tmp/win7-upgrade-src; mkdir /tmp/win7-upgrade-src; tar -xzf /tmp/win7-upgrade.tgz -C /tmp/win7-upgrade-src; '
         '/tmp/win7-upgrade-src/install.sh', timeout=600)
    CLI = '/home/tester/.local/bin/win7-classic'


def compositor_pid():
    return user('pgrep -u tester -x kwin_wayland')


def decoration():
    return user("qdbus6 org.kde.KWin /KWin supportInformation | sed -n '/^Decoration$/,/^Output backend$/p'")


def main():
    global CLI
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    if user('win7-classic status', check=False) == 'windows':
        mode('current')
    close_test_apps()
    old = build_package(OLD)
    root(f'cp {old} /tmp/win7-classic-old.pkg.tar.zst')
    new = build_package()
    root(f'cp {new} /tmp/win7-classic-new.pkg.tar.zst')
    # build_package() also left the exact current-tree archive for the development-install route.
    for route in ('development', 'package'):
        close_test_apps()
        if user('win7-classic status', check=False) == 'windows':
            mode('current')
        remove_user_install()
        CLI = '/usr/bin/win7-classic'
        root('pacman -U --noconfirm /tmp/win7-classic-old.pkg.tar.zst >/tmp/upgrade-old-pacman.log 2>&1')
        # Only test setup starts a clean OLD compositor; the measured upgrade below never restarts it.
        restart_sddm()
        wait_for(logged_in, 'old-version lab session', 90)
        time.sleep(5)
        user('systemctl --user restart xdg-desktop-portal.service')
        assert_portal_display()
        if route == 'development':
            development_install(OLD)
        pid = compositor_pid()
        frames.OUT = OUT / route
        frames.OUT.mkdir(exist_ok=True)
        frames.start_fixture()
        before = frames.config_snapshot()
        mode('windows')
        frames.fixture(frames.WINDOW)
        vmctl.pointer(VM, 100, 400)
        shot(frames.OUT / 'old-windows.png')
        maps = root(f'grep win7-classic /proc/{pid}/maps')
        (frames.OUT / 'old-kwin-maps.txt').write_text(maps)
        assert '/win7-classic/primitives/libwin7classicqml.so' in maps, 'old QML module never loaded'
        mode('current')
        if route == 'development':
            development_install(UNVERSIONED)
            mode('windows')  # The unversioned build can retain an old component or accept a substitute.
            broken = decoration()
            (frames.OUT / 'unversioned-decoration.txt').write_text(broken)
            shot(frames.OUT / 'unversioned-upgrade.png')
            stale = frames.frame_diff(frames.OUT / 'unversioned-upgrade.png', frames.REF / 'w7-taskbar.png',
                                      (256, 120, 1024, 680), [frames.CLIENT, frames.ICON, frames.TEXT])
            assert stale, 'unversioned upgrade unexpectedly loaded fresh caption code'
            (frames.OUT / 'stale-frame-pixels.txt').write_text(str(len(stale)))
            mode('current')
            development_install()
        else:
            root('pacman -U --noconfirm /tmp/win7-classic-new.pkg.tar.zst >/tmp/upgrade-new-pacman.log 2>&1')
        if route == 'development':
            qml = '~/.local/share/kwin/decorations/win7classic2/contents/ui/main.qml'
            user(f'cp {qml} /tmp/upgrade-held.qml; sed -i s/captionActive:/unknownCaptionProperty:/ {qml}')
            try:
                failure = mode('windows', expect_ok=False)
                assert 'KWin rejected the Classic decoration' in failure, failure
                assert user('win7-classic status') == 'current'
                assert compositor_pid() == pid
                (frames.OUT / 'rejected-decoration.log').write_text(failure)
            finally:
                user(f'cp /tmp/upgrade-held.qml {qml}')
            print('broken decoration rejected loudly and rolled back without restarting KWin')
        for attempt in range(3):
            mode('windows')
            assert compositor_pid() == pid, 'upgrade/switch restarted KWin'
            frames.fixture(frames.WINDOW)
            vmctl.pointer(VM, 100, 400)
            time.sleep(0.5)
            frames.assert_frame(f'upgraded-{attempt}', 'w7-taskbar.png', (256, 120, 1024, 680),
                                [frames.CLIENT, frames.ICON, frames.TEXT])
            maps = root(f'grep win7-classic /proc/{pid}/maps')
            assert '/win7-classic/primitives2/libwin7classicqml2.so' in maps, 'new QML module did not load'
            (frames.OUT / 'upgraded-kwin-maps.txt').write_text(maps)
            mode('current')
            assert compositor_pid() == pid
        assert frames.config_snapshot() == before, 'upgrade round trip changed current-mode appearance'
        (frames.OUT / 'kwin-pid.txt').write_text(pid)
        (frames.OUT / 'journal.txt').write_text(user('journalctl --user -b -u plasma-kwin_wayland --no-pager -o cat'))
        print(route, 'old activation -> current -> upgrade -> repeated exact frames/current, unchanged KWin PID', pid)
    close_test_apps()
    root('pacman -Rns --noconfirm win7-classic >/tmp/upgrade-remove.log 2>&1')
    print('ALL CLASSIC UPGRADE CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
