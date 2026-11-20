#!/usr/bin/env python3
"""SDDM login theme (issue #15), installed from the package, with the tester account's real password.

The theme is selected the way an administrator would (an sddm.conf.d drop-in). Logging the tester out shows the
greeter; a wrong password must be rejected and the right one must start the Plasma session. A broken theme must
still allow logging in (SDDM's embedded fallback).
"""
import argparse
from pathlib import Path
import time

from PIL import Image, ImageChops, ImageStat

from lab import ROOT, VM, vmctl, shot, wait_for, user, assert_portal_display
from test_lock import PASSWORD, assert_logon_art, field_band, type_password
from test_package import build_package, root

OUT = Path('/tmp/win7-login-test')
REF = ROOT / 'reference/screenshots/w7-login.png'
CONF = '/etc/sddm.conf.d/zz-win7-classic-test.conf'


def logged_in():
    return root('pgrep -u tester -x plasmashell >/dev/null && echo yes || echo no') == 'yes'


def greeter():
    return root('pgrep sddm-greeter >/dev/null && echo yes || echo no') == 'yes'


def restart_sddm():
    # SDDM alone can leave the old user manager/Plasma alive, falsely appearing to be a successful login.
    try:
        root('systemctl stop sddm')
        root('set -e; if loginctl show-user tester >/dev/null 2>&1; then loginctl terminate-user tester; fi; '
             'systemctl stop user@$(id -u tester).service')
    finally:
        root('systemctl start sddm')


def assert_single_account_layout(path, reference):
    """Compare the password field and the wallpaper where a second-account control would appear."""
    assert field_band(path) == field_band(reference) == (512, 532)
    actual, target = (Image.open(p).convert('RGB') for p in (path, reference))
    assert actual.size == target.size == (1280, 800)
    for image in (actual, target):
        # Measure the solid field edges around the placeholder, not the label or account image.
        x = [x for x in range(510, 754) if min(image.getpixel((x, 522))) > 235]
        assert x and abs(x[0] - 529) <= 1 and abs(x[-1] - 749) <= 1, x
    box = (570, 570, 710, 654)
    mae = sum(ImageStat.Stat(ImageChops.difference(actual.crop(box), target.crop(box))).mean) / 3
    assert mae < 3, f'unexpected control below the single-account password field: RGB MAE {mae:.3f}'
    print(f'single-account center: field rows 512–532 and no Switch User (RGB MAE {mae:.3f})')


def assert_greeter_footer(path, reference):
    """Require both halves of the power control independently of the keyboard button."""
    actual, target = (Image.open(p).convert('RGB') for p in (path, reference))
    assert actual.size == target.size == (1280, 800)
    differences = {}
    for label, box in (
        ('accessibility', (34, 738, 72, 766)),
        ('power primary', (1188, 738, 1226, 766)),
        ('power arrow', (1226, 738, 1246, 766)),
    ):
        mae = sum(ImageStat.Stat(ImageChops.difference(actual.crop(box), target.crop(box))).mean) / 3
        differences[label] = mae
        print(f'SDDM {label}: RGB MAE {mae:.3f}')
    assert max(differences.values()) < 5, differences


def capture_closed_prompt(path):
    # Qt may open its keyboard on password focus. Dismiss it through the real theme action.
    vmctl.pointer(VM, 610, 430)
    shot(path)
    with Image.open(path) as actual, Image.open(REF) as reference:
        keyboard_open = actual.convert('RGB').getpixel((250, 620)) != reference.convert('RGB').getpixel((250, 620))
    if keyboard_open:
        vmctl.pointer(VM, 53, 752, 'left')
        vmctl.pointer(VM, 610, 430)
        time.sleep(1)
        shot(path)


def assert_power_popup(path, closed_path, *, opened):
    actual, closed = (Image.open(p).convert('RGB') for p in (path, closed_path))
    assert actual.size == closed.size == (1280, 800)
    # This region is wallpaper when the menu is closed, and excludes both the pointer and the arrow.
    menu = (1090, 580, 1246, 737)
    mae = sum(ImageStat.Stat(ImageChops.difference(actual.crop(menu), closed.crop(menu))).mean) / 3
    assert (mae > 10 if opened else mae < 1), f'{path.name}: unexpected popup state (RGB MAE {mae:.3f})'
    assert actual.getpixel((250, 620)) == closed.getpixel((250, 620)), f'{path.name}: virtual keyboard reopened'
    assert field_band(path) == (512, 532), f'{path.name}: password field moved'
    arrow = (1226, 738, 1246, 766)
    assert ImageChops.difference(actual.crop(arrow), closed.crop(arrow)).getbbox() is None, f'{path.name}: power arrow disappeared'
    print(f'{path.name}: popup {"open" if opened else "closed"}, keyboard closed, arrow and password field visible (RGB MAE {mae:.3f})')


def dismiss_power_popup(prefix, closed_path, *, escape):
    opened = OUT / f'{prefix}-open.png'
    dismissed = OUT / f'{prefix}-dismissed.png'
    vmctl.pointer(VM, 1237, 752, 'left')
    vmctl.pointer(VM, 1040, 600)
    time.sleep(.5)
    shot(opened)
    assert_power_popup(opened, closed_path, opened=True)
    if escape:
        vmctl.keys(VM, 'KEY_ESC')
    else:
        vmctl.pointer(VM, 1040, 600, 'left')
    time.sleep(.5)
    shot(dismissed)
    assert_power_popup(dismissed, closed_path, opened=False)


def verify_login(prefix, power_popup=False):
    type_password('wrong-password')
    time.sleep(6)
    shot(OUT / f'{prefix}-wrong-password.png')
    assert not logged_in() and greeter(), 'a wrong password logged in'
    assert field_band(OUT / f'{prefix}-wrong-password.png') is None, 'no error shown after a wrong password'
    print(f'{prefix}: wrong password rejected with an error')

    vmctl.keys(VM, 'KEY_ENTER')  # OK
    time.sleep(1)
    if power_popup:
        closed = OUT / f'{prefix}-before-power.png'
        capture_closed_prompt(closed)
        assert_greeter_footer(closed, REF)
        vmctl.type_text(VM, PASSWORD[:4])
        dismiss_power_popup(f'{prefix}-escape', closed, escape=True)
        vmctl.type_text(VM, PASSWORD[4:8])  # No click in the field after either dismissal.
        dismiss_power_popup(f'{prefix}-click-away', closed, escape=False)
        type_password(PASSWORD[8:])
    else:
        type_password(PASSWORD)
    wait_for(logged_in, f'{prefix}: right password starts the Plasma session', 60)
    time.sleep(8)
    shot(OUT / f'{prefix}-logged-in.png')
    print(f'{prefix}: right password accepted and Plasma started')


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path, nargs='?', default=OUT)
    parser.add_argument('--installed', action='store_true', help='test the already installed candidate package')
    args = parser.parse_args()
    OUT = args.outdir
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    vmctl.start(VM)
    if not args.installed:
        root('if ! pacman -Qo /usr/lib/qt6/plugins/styles/libwin7classicstyle.so >/dev/null 2>&1; then rm -f /usr/lib/qt6/plugins/styles/libwin7classicstyle.so; fi')
        package = build_package()
        root(f'pacman -U --noconfirm {package} >/tmp/pacman-install.log 2>&1 || {{ cat /tmp/pacman-install.log; exit 1; }}')
    assert root('test -f /usr/share/sddm/themes/win7-classic/Main.qml && echo ok') == 'ok', 'package did not install the SDDM theme'
    # The lab normally autologins tester (vm/prepare-tester.sh); this drop-in sorts after it and turns that off.
    root(f'mkdir -p /etc/sddm.conf.d && printf "[Theme]\\nCurrent=win7-classic\\n[General]\\nDisplayServer=x11\\nInputMethod=qtvirtualkeyboard\\n[Autologin]\\nUser=\\n" > {CONF}')
    try:
        restart_sddm()
        wait_for(greeter, 'SDDM greeter', 60)
        time.sleep(5)
        shot(OUT / '0-users.png')
        vmctl.pointer(VM, 560, 380)  # X ignores a click before the pointer's first motion
        vmctl.pointer(VM, 563, 386, 'left')  # tester's tile; the lab VM also has the older account w
        time.sleep(1)
        capture_closed_prompt(OUT / '0-selected-with-chooser.png')
        assert_logon_art(OUT / '0-selected-with-chooser.png', REF)
        try:
            assert_single_account_layout(OUT / '0-selected-with-chooser.png', REF)
        except AssertionError as error:
            assert 'unexpected control' in str(error), error
            print(f'Expected multi-account mismatch: {error}')
        else:
            raise AssertionError('multi-account selection has no visible Switch User')
        vmctl.pointer(VM, 640, 625, 'left')
        time.sleep(1)
        shot(OUT / '0-returned-to-chooser.png')
        assert field_band(OUT / '0-returned-to-chooser.png') is None, 'Switch User did not return to the account chooser'
        vmctl.pointer(VM, 563, 386, 'left')
        time.sleep(1)
        verify_login('multi-account')

        # Only in the stock lab (tester UID 1001, the older account UID 1000). No account is modified.
        root(f'printf "\\n[Users]\\nMinimumUid=1001\\nMaximumUid=1001\\n" >> {CONF}')
        restart_sddm()
        wait_for(greeter, 'single-account SDDM greeter', 60)
        time.sleep(5)
        xorg = root('pgrep -a -x Xorg || true')
        assert '-seat seat0' in xorg and not logged_in(), 'not at the installed X11 greeter'
        print(xorg)
        capture_closed_prompt(OUT / '1-login.png')
        assert_logon_art(OUT / '1-login.png', REF)
        assert_single_account_layout(OUT / '1-login.png', REF)
        assert_greeter_footer(OUT / '1-login.png', REF)

        verify_login('single-account', power_popup=True)

        ui = '/usr/share/sddm/themes/win7-classic/LogonUi.qml'
        backup = root(f'backup=$(mktemp); cp -p {ui} "$backup"; printf "%s" "$backup"')
        try:
            root(f'echo "this is not QML" >> {ui}')
            restart_sddm()
            wait_for(greeter, 'SDDM greeter with a broken theme', 60)
            time.sleep(8)
            shot(OUT / '4-broken-theme.png')
            assert 'Fallback to embedded theme' in root('journalctl -b --since "-1min" -o cat'), 'SDDM did not fall back'
            type_password(PASSWORD)
            wait_for(logged_in, 'login through SDDM fallback theme', 60)
            print("a broken theme falls back to SDDM's embedded one, and logging in still works")
        finally:
            root(f'mv -f {backup} {ui}')
    finally:
        root(f'rm -f {CONF}')
        if not args.installed:
            root('pacman -R --noconfirm win7-classic >/dev/null')
        if not logged_in():
            restart_sddm()  # back to autologin for the other tests
            wait_for(logged_in, 'tester autologin restored', 60)
        # Forced SDDM transitions can activate the portal before the new session exports its display.
        user('systemctl --user restart xdg-desktop-portal.service')
        assert_portal_display()
    print('ALL LOGIN CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
