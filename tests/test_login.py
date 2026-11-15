#!/usr/bin/env python3
"""SDDM login theme (issue #15), installed from the package, with the tester account's real password.

The theme is selected the way an administrator would (an sddm.conf.d drop-in). Logging the tester out shows the
greeter; a wrong password must be rejected and the right one must start the Plasma session. A broken theme must
still allow logging in (SDDM's embedded fallback).
"""
from pathlib import Path
import sys
import time

from lab import ROOT, VM, vmctl, shot, wait_for
from test_lock import PASSWORD, field_band, type_password
from test_package import build_package, root

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-login-test')
REF = ROOT / 'reference/screenshots/w7-login.png'
CONF = '/etc/sddm.conf.d/zz-win7-classic-test.conf'


def logged_in():
    return root('pgrep -u tester -x plasmashell >/dev/null && echo yes || echo no') == 'yes'


def greeter():
    return root('pgrep sddm-greeter >/dev/null && echo yes || echo no') == 'yes'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    vmctl.start(VM)
    package = build_package()
    root(f'pacman -U --noconfirm {package} >/tmp/pacman-install.log 2>&1 || {{ cat /tmp/pacman-install.log; exit 1; }}')
    assert root('test -f /usr/share/sddm/themes/win7-classic/Main.qml && echo ok') == 'ok', 'package did not install the SDDM theme'
    # The lab normally autologins tester (vm/prepare-tester.sh); this drop-in sorts after it and turns that off.
    root(f'mkdir -p /etc/sddm.conf.d && printf "[Theme]\\nCurrent=win7-classic\\n[Autologin]\\nUser=\\n" > {CONF}')
    try:
        root('systemctl restart sddm')
        wait_for(greeter, 'SDDM greeter', 60)
        time.sleep(5)
        shot(OUT / '0-users.png')
        vmctl.pointer(VM, 560, 380)  # X ignores a click before the pointer's first motion
        vmctl.pointer(VM, 563, 386, 'left')  # tester's tile; the lab VM also has the older account w
        time.sleep(1)
        shot(OUT / '1-login.png')
        ours, reference = field_band(OUT / '1-login.png'), field_band(REF)
        assert ours and abs(ours[0] - reference[0]) <= 2 and abs(ours[1] - reference[1]) <= 2, f'password field rows {ours}, Windows {reference}'
        print(f'Windows logon screen: password field where Windows has it (rows {ours}, Windows {reference})')

        type_password('wrong-password')
        time.sleep(6)
        shot(OUT / '2-wrong-password.png')
        assert not logged_in() and greeter(), 'a wrong password logged in'
        assert field_band(OUT / '2-wrong-password.png') is None, 'no error shown after a wrong password'
        print('wrong password: error shown, not logged in')

        vmctl.keys(VM, 'KEY_ENTER')  # OK
        time.sleep(1)
        type_password(PASSWORD)
        wait_for(logged_in, 'right password starts the Plasma session', 60)
        time.sleep(8)
        shot(OUT / '3-logged-in.png')
        print('right password: Plasma session started')

        root('echo "this is not QML" >> /usr/share/sddm/themes/win7-classic/LogonUi.qml; systemctl restart sddm')
        wait_for(greeter, 'SDDM greeter with a broken theme', 60)
        time.sleep(8)
        shot(OUT / '4-broken-theme.png')
        assert 'Fallback to embedded theme' in root('journalctl -b --since "-1min" -o cat'), 'SDDM did not fall back'
        type_password(PASSWORD)
        wait_for(logged_in, 'login through SDDM fallback theme', 60)
        print("a broken theme falls back to SDDM's embedded one, and logging in still works")
    finally:
        root(f'rm -f {CONF}; pacman -Q win7-classic >/dev/null 2>&1 && pacman -Rns --noconfirm win7-classic >/dev/null; true')
        if not logged_in():
            root('systemctl restart sddm')  # back to autologin for the other tests
            wait_for(logged_in, 'tester autologin restored', 60)
    print('ALL LOGIN CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
