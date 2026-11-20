#!/usr/bin/env python3
"""Run against the installed Classic lock on the lab seat, with SDDM Relogin=false.

The normal pam_unix failure delay leaves time for a real pointer click while
an incorrect password is pending. No PAM configuration or QML is modified.
"""
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from lab import VM, shot, user, vmctl, wait_for
import test_lock as lock


def seat():
    return vmctl.run(VM, 'loginctl show-seat seat0 -p ActiveSession --value', 5)[1].strip()


def difference(a, b, box):
    with Image.open(a) as x, Image.open(b) as y:
        return sum(ImageStat.Stat(ImageChops.difference(
            x.convert('RGB').crop(box), y.convert('RGB').crop(box))).mean) / 3


def assert_switch_click_ignored(out):
    """Enter with a wrong password, click before the error, then retry normally."""
    original = seat()
    assert original and lock.locked()
    vmctl.type_text(VM, 'incorrect-lab')
    vmctl.pointer(VM, 640, 594)
    before = out / 'pending-before.png'
    pending = out / 'pending-before-click.png'
    after = out / 'pending-after-click.png'
    error = out / 'pending-error.png'
    shot(before)
    start = time.monotonic()
    vmctl.keys(VM, 'KEY_ENTER')
    shot(pending)
    vmctl.button(VM, 'left', True)
    vmctl.button(VM, 'left', False)
    elapsed = time.monotonic() - start
    shot(after)
    print(f'Physical click completed {elapsed:.3f}s after submitting wrong password')
    # The prompt disappears when PAM's error arrives; capturing it just before
    # the click rules out clicking an already rejected password attempt.
    assert lock.field_band(before) == lock.field_band(pending) == (498, 518)
    time.sleep(4)
    active = seat()
    shot(error)
    _, details, _ = vmctl.run(VM, f'loginctl show-session {active} -p Class -p Active', 5)
    print(f'Seat before/after pending click: {original}/{active}; locked={lock.locked()}; {details.strip()}')
    assert active == original, 'Switch User activated during the pending password attempt'
    assert lock.field_band(after) == (498, 518), 'password attempt was no longer pending at click release'
    assert lock.locked() and lock.field_band(error) is None, 'PAM did not reject the submitted password'
    for box in ((586, 580, 602, 607), (678, 580, 694, 607)):
        assert difference(pending, error, box) < 1, 'Switch User artwork still visible while authentication is pending'
        assert difference(before, pending, box) > 20, 'Switch User was not actionable before authentication'
    vmctl.keys(VM, 'KEY_ENTER')  # Dismiss the password error.
    time.sleep(.6)
    shot(out / 'pending-retry.png')
    assert lock.field_band(out / 'pending-retry.png') == (498, 518)
    lock.type_password(lock.PASSWORD)
    wait_for(lambda: not lock.locked(), 'real unlock after pending Switch User click', 20)
    assert seat() == original
    print('Pending switch click ignored; real wrong password rejected and right retry unlocked the same session')


if __name__ == '__main__':
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    assert user('win7-classic status') == 'windows'
    lock.OUT = out
    lock.lock('locked.png')
    assert_switch_click_ignored(out)
