#!/usr/bin/env python3
"""A slow mounted destination must not delay real taskbar actions or retain stale rows."""
from contextlib import ExitStack
import json
from pathlib import Path
import shlex

from PIL import Image
import sys
import time

from explorer_frequent_fixture import TREE, current, fixture, stash, stop_folder_explorers, unit
from lab import VM, activate, kwin_query, shot, toggle, user, vmctl, wait_for, windows
from test_explorer_frequent import APP, PROFILE, STATE, explorer, go, key, ocr, own_home_window, panel, popup
from test_explorer_frequent_privacy import CONFIG, STORE, dismissed, policy, root


ACTIVITIES = 'qdbus6 org.kde.ActivityManager /ActivityManager/Activities org.kde.ActivityManager.Activities.'
RESTART = 'systemctl --user restart plasma-kactivitymanagerd'


def activity_call(method, *args):
    return user(ACTIVITIES + method + ''.join(' ' + shlex.quote(arg) for arg in args))


def private_activity(activity):
    feature = f'org.kde.ActivityManager.Resources.Scoring/isOTR/{activity}'
    result = user('qdbus6 org.kde.ActivityManager /ActivityManager/Features '
                  f'org.kde.ActivityManager.Features.GetValue {shlex.quote(feature)}')
    assert result in ('true', 'false'), result
    return result


def stash_policy(restore, name='policy'):
    activity = activity_call('CurrentActivity')
    fingerprint = lambda: user(f'if test -e "{CONFIG}"; then sha256sum "{CONFIG}"; else echo absent; fi')
    expected = (fingerprint(), private_activity(activity))

    def verify():
        actual = (fingerprint(), private_activity(activity))
        assert actual == expected, (expected, actual)
        print(f'Restored exact policy {actual[0]}; live daemon Activity off the record={actual[1]}')

    restore.callback(verify)
    restore.callback(user, RESTART)
    stash(restore, CONFIG, name)


def restore_policy(restore):
    stash_policy(restore, 'original-policy')
    activity = activity_call('CurrentActivity')
    policy('off-the-record-activities', activity)
    user(RESTART)
    assert private_activity(activity) == 'true'
    with ExitStack() as temporary:
        stash_policy(temporary)
        policy('what-to-remember', '0')
        policy('off-the-record-activities', '')
        user(RESTART)
        assert private_activity(activity) == 'false'
    assert private_activity(activity) == 'true'


def switch_activity(activity):
    assert activity_call('SetCurrentActivity', activity) == 'true'
    wait_for(lambda: kwin_query('emit(workspace.currentActivity);') == [[activity]], 'KWin switched Activity')


def queued_visit(out, restore, scenario):
    stash_policy(restore)
    user(f'mkdir {TREE}/{{SeedA,SeedB,Held,Denied}}')
    policy('what-to-remember', '0')
    if scenario == 'queued-alias':
        user(f'mkdir {TREE}/Allowed; touch {TREE}/Allowed/not-the-listed-folder; ln -s Denied {TREE}/Alias')
        policy('url-filters', f'{TREE}/Denied*')
    if scenario == 'queued-activity':
        public = activity_call('CurrentActivity')
        private = activity_call('AddActivity', 'w7f35 private listing')
        assert private and private != public
        restore.callback(activity_call, 'RemoveActivity', private)
        restore.callback(activity_call, 'SetCurrentActivity', public)
        policy('off-the-record-activities', private)
        user(RESTART)
        assert private_activity(public) == 'false' and private_activity(private) == 'true'
        user(f'mkdir {TREE}/ListingMount')
        unit(restore, f'{TREE}/fs -f -o attr_timeout=0,entry_timeout=0,negative_timeout=0 {TREE}/ListingMount')
        wait_for(lambda: user(f'mountpoint -q {TREE}/ListingMount && echo ready', check=False) == 'ready', 'listing mount ready')
        restore.callback(user, f'fusermount3 -uz {TREE}/ListingMount')
        restore.callback(user, f'rm -f {TREE}/listing-slow')
    toggle('windows')
    panel('w.writeConfig("launchers", ["applications:org.win7classic.explorer.desktop"]);')
    vmctl.pointer(VM, 85, 778, 'left')
    own_home_window(restore, 'real Explorer pin starts the queue test')
    pid = user('pgrep -x win7-explorer')
    for folder in ('SeedA', 'SeedB', 'SeedA'):
        go(folder)
    wait_for(lambda: user(f'cat "{STORE}"', check=False) ==
             f'[["{TREE}/SeedA",2],["{TREE}/SeedB",1]]', 'trained history through real visits')
    # Keep an independent copy of the real bytes below the mount, not underneath a stalled lookup.
    user(f'cp "{STORE}" {TREE}/original-counts')
    unit(restore, f'{TREE}/fs -f -o attr_timeout=0,entry_timeout=0,negative_timeout=0 "{STATE}"')
    wait_for(lambda: user(f'mountpoint -q "{STATE}" && echo ready', check=False) == 'ready', 'history overmount ready')
    restore.callback(user, f'if mountpoint -q "{STATE}"; then fusermount3 -uz "{STATE}"; fi')
    restore.callback(user, f'rm -f {TREE}/slow')
    user(f'touch {TREE}/slow')
    go('Held')
    held = lambda: user(f'test -e {TREE}/pending -a -e {TREE}/slow && echo pending', check=False) == 'pending'
    wait_for(held, 'earlier history I/O stalled in the real kernel request')
    if scenario == 'queued-current':
        toggle('current')
        assert user('~/.local/bin/win7-classic status') == 'current'
    elif scenario == 'queued-policy':
        policy('what-to-remember', '2')
    if scenario == 'queued-activity':
        assert kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass === "{APP}" && w.pid === {pid}) {{ w.activities = []; emit(w.activities.length); }}') == [['0']]
        user(f'touch {TREE}/listing-slow')
        go('ListingMount/Listing', caption='Listing')
        wait_for(lambda: user(f'test -e {TREE}/listing-pending && echo pending', check=False) == 'pending',
                 'KIO already started the real listing while the public Activity was active')
        switch_activity(private)
        assert kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass === "{APP}" && w.pid === {pid}) {{ workspace.activeWindow = w; emit(w.caption); }}') == [['Listing']]
        assert held() and activity_call('CurrentActivity') == private
        user(f'rm -f {TREE}/listing-slow')
    else:
        go('Alias' if scenario == 'queued-alias' else 'Denied')
    # This empty folder label is shown only after listingDirCompleted, not simply on urlEntered.
    assert user('pgrep -x win7-explorer') == pid and held()
    path = out / 'denied-listing-while-held.png'
    def listed():
        shot(path)
        with Image.open(path) as image:
            return 'empty.' in ocr(out, 'listing-completed', image, (0, 0, 1280, 750))
    wait_for(listed, 'Explorer completed the real empty listing while the writer remained held')
    if scenario == 'queued-current':
        toggle('windows')
    elif scenario == 'queued-policy':
        policy('what-to-remember', '0')
    elif scenario == 'queued-activity':
        assert held() and activity_call('CurrentActivity') == private
        switch_activity(public)
        assert activity_call('CurrentActivity') == public
    else:
        assert user(f'readlink {TREE}/Alias') == 'Denied'
        user(f'ln -sfn Allowed {TREE}/Alias')
        assert user(f'readlink {TREE}/Alias') == 'Allowed'
    assert user('~/.local/bin/win7-classic status') == 'windows' and held()
    # The old request retains its mount, but the queued visit will see the restored real count file.
    user(f'fusermount3 -uz "{STATE}"')
    assert held()
    user(f'rm -f {TREE}/slow')
    key('LEFTCTRL', 'W')
    wait_for(lambda: user(f'test ! -e /proc/{pid}/stat && echo exited', check=False) == 'exited',
             'Explorer exited after draining its serial history worker')
    before = user(f'sha256sum {TREE}/original-counts').split()[0]
    after = user(f'sha256sum "{STORE}"').split()[0]
    print(f'{scenario}: before={before}, after={after}; counts={user(f"cat {STORE}")}')
    user(f'cmp -- {TREE}/original-counts "{STORE}"')


def held_policy(out, restore, scenario):
    stash_policy(restore)
    user(f'mkdir {TREE}/{{Policy,LocalA,LocalB}}')
    policy('what-to-remember', '2')
    wanted = user(f'sha256sum "{CONFIG}"').split()[0]
    toggle('windows')
    panel('w.writeConfig("launchers", ["applications:org.win7classic.explorer.desktop"]);')
    if scenario == 'policy-explorer':
        vmctl.pointer(VM, 85, 778, 'left')
        own_home_window(restore, 'Explorer ready before holding privacy inputs')
        pid = user('pgrep -x win7-explorer')
    # A file bind holds only this real KConfig input, not other KDE settings or the count store.
    root(f'systemd-run --collect -q --unit=w7-35-held-policy {TREE}/fs -f -o allow_other,attr_timeout=0,entry_timeout=0,negative_timeout=0 {TREE}/Policy')
    restore.callback(root, f'systemctl stop w7-35-held-policy.service; if mountpoint -q {TREE}/Policy; then umount {TREE}/Policy; fi')
    wait_for(lambda: user(f'mountpoint -q {TREE}/Policy && echo ready', check=False) == 'ready', 'policy filesystem mounted')
    config = user(f'printf "%s" "{CONFIG}"')
    root(f'mount --bind {TREE}/Policy/kactivitymanagerd-pluginsrc {config}')
    restore.callback(root, f'umount {config}')
    restore.callback(user, f'rm -f {TREE}/policy-slow')
    assert user(f'sha256sum "{CONFIG}"').split()[0] == wanted, 'fixture must return the exact existing Do not remember setting'
    user(f'touch {TREE}/policy-slow')
    pending = lambda: user(f'test -e {TREE}/policy-slow -a -e {TREE}/policy-pending && echo pending', check=False) == 'pending'
    if scenario == 'policy-explorer':
        key('LEFTALT', 'D')
        vmctl.type_text(VM, f'{TREE}/LocalA\n')
        wait_for(pending, 'real policy lookup held in the kernel during navigation')
        wait_for(lambda: (explorer() or ('',))[0] == 'LocalA', 'navigate while policy, not counts, is held', timeout=3)
        go('LocalB')
        assert pending() and user('pgrep -x win7-explorer') == pid
        path = out / 'policy-held-navigation.png'
        shot(path)
        with Image.open(path) as image:
            assert 'empty.' in ocr(out, 'policy-listing-completed', image, (0, 0, 1280, 750))
        key('LEFTCTRL', 'W')
        wait_for(lambda: explorer() is None, 'close the same Explorer before the policy lookup returns', timeout=3)
        assert pending()
        shot(out / 'policy-held-closed.png')
        user(f'rm -f {TREE}/policy-slow')
        wait_for(lambda: user(f'test ! -e /proc/{pid}/stat && echo exited', check=False) == 'exited', 'Explorer drained after releasing policy')
        assert user(f'test ! -e "{STORE}" && echo absent') == 'absent'
        print('Two real folder listings and Ctrl+W before the held policy lookup returned; abandoned visits did not create history.')
    else:
        start = user('date +"%Y-%m-%d %H:%M:%S.%6N"')
        image, x, y = popup(out, 'delayed-denial-initial', 0, launcher=True, unavailable=True)
        assert pending() and ocr(out, 'delayed-denial-initial', image, (x + 5, y + 3, x + 170, y + 42)) == ['Frequent', 'Frequent', 'unavailable']
        assert 'Frequent unavailable: initial check timed out' in user(f"journalctl --user -u plasma-plasmashell --since '{start}' --no-pager")
        key('ESC')
        wait_for(lambda: dismissed(out, 'delayed-denial-escaped', x, y), 'dismiss the first mapped diagnostic')
        reopened, x2, y2 = popup(out, 'delayed-denial-reopened-while-held', 0, launcher=True, unavailable=True)
        assert (x2, y2) == (x, y) and pending()
        assert ocr(out, 'delayed-denial-reopened-while-held', reopened, (x2 + 5, y2 + 3, x2 + 170, y2 + 42)) == ['Frequent', 'Frequent', 'unavailable']
        # Closing and reopening during I/O must leave every action row at the same coordinates and pixels.
        assert image.crop((x, y + 43, x + 230, y + 93)).tobytes() == reopened.crop((x, y + 43, x + 230, y + 93)).tobytes()
        user(f'rm -f {TREE}/policy-slow')
        wait_for(lambda: dismissed(out, 'delayed-denial-dismissed', x, y), 'confirmed privacy denial dismisses mapped diagnostic', timeout=3)
        popup(out, 'delayed-denial-reopened', 0, launcher=True)
        key('UP'); key('UP'); key('ENTER')
        own_home_window(restore, 'Launch works on reopening the denied action-only menu')
        key('LEFTCTRL', 'W')
        wait_for(lambda: explorer() is None, 'Explorer closes')
        print('Real Do not remember reply arrived after timeout and dismissed the diagnostic; reopened action-only menu launches.')


def click_away_while_pending(out, restore, arm, pending, release):
    other = 'org.kde.konsole'
    assert other not in windows(), 'Konsole must belong to this test'
    unit(restore, 'konsole --separate')
    wait_for(lambda: other in windows(), 'real Konsole window')
    assert kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass === "{other}") {{ '
                      'w.frameGeometry = {x: 480, y: 90, width: 320, height: 260}; emit(w.resourceClass); }') == [[other]]
    activate(other)
    vmctl.pointer(VM, 600, 220)
    box = (0, 590, 230, 756)

    def crop(name):
        path = out / f'{name}.png'
        shot(path)
        with Image.open(path) as image:
            return image.crop(box).tobytes()

    # Match the after-click pointer location; panel hover artwork may extend above the panel.
    before = crop('before')
    vmctl.pointer(VM, 85, 778)
    arm()
    def send(events):
        vmctl.virsh('qemu-monitor-command', VM, json.dumps({
            'execute': 'input-send-event', 'arguments': {'events': events}}))

    def button(name, down):
        return {'type': 'btn', 'data': {'button': name, 'down': down}}

    send([button('right', True)])
    start = time.monotonic()
    send([button('right', False)])
    # Poll in the guest without lab.user's half-second agent wait interval.
    marker = vmctl.agent(VM, 'guest-exec', {'path': '/usr/bin/timeout', 'arg': ['.3s', '/usr/bin/bash', '-c',
        f'until test -e {TREE}/pending; do sleep .002; done'], 'capture-output': True})['pid']
    while not (state := vmctl.agent(VM, 'guest-exec-status', {'pid': marker})).get('exited'):
        assert time.monotonic() - start < .16, 'real VFS request did not start before initial deadline'
    assert state['exitcode'] == 0
    send([{'type': 'abs', 'data': {'axis': axis, 'value': round((pixel + .5) * 32768 / extent)}}
          for axis, pixel, extent in (('x', 600, 1280), ('y', 220, 800))])
    send([button('left', True)])
    send([button('left', False)])
    elapsed = time.monotonic() - start
    print(f'Real VFS request observed before clicking the already-focused Konsole ({elapsed * 1000:.0f} ms)')
    assert elapsed < .18, 'click-away input must precede the initial timeout'
    time.sleep(.3)
    assert pending(), 'query must remain held past initial deadline'
    assert crop('after-click-while-held') == before, 'abandoned pending query mapped a jump list at timeout'
    assert windows()[other][1], 'Konsole lost focus to abandoned query'
    release()
    assert crop('after-release') == before, 'late reply mapped the abandoned jump list'
    assert windows()[other][1], 'Konsole lost focus to the late reply'
    popup(out, 'explicit-reopen', 1, launcher=True)
    key('ESC')
    print('No popup during the held query or after release; an explicit right-click still shows the real history.')


def main(out, source, scenario):
    out.mkdir(parents=True, exist_ok=True)
    assert user('~/.local/bin/win7-classic status') == 'current'
    assert explorer() is None, 'the Explorer task button must belong to the test'
    with fixture('Share') as restore:
        stash(restore, STATE, 'history')
        stash(restore, PROFILE, 'profile')
        restore.callback(current)
        restore.callback(stop_folder_explorers)
        user(f'cc -Wall -Wextra {source}/tests/explorer-frequent/slow-share.c -o {TREE}/fs $(pkg-config --cflags --libs fuse3)')
        if scenario == 'restore-policy':
            restore_policy(restore)
            return
        if scenario.startswith('queued-'):
            queued_visit(out, restore, scenario)
            return
        if scenario in ('policy-explorer', 'delayed-denial'):
            held_policy(out, restore, scenario)
            return
        if scenario == 'explorer':
            user(f'mkdir -m700 "{STATE}" {TREE}/{{LocalA,LocalB}}')
            unit(restore, f'{TREE}/fs -f -o attr_timeout=0,entry_timeout=0,negative_timeout=0 "{STATE}"')
            wait_for(lambda: user(f'mountpoint -q "{STATE}" && echo ready', check=False) == 'ready', 'history fixture mounted')
            restore.callback(user, f'fusermount3 -u "{STATE}"')
            restore.callback(user, f'rm -f {TREE}/slow')
            toggle('windows')
            panel('w.writeConfig("launchers", ["applications:org.win7classic.explorer.desktop"]);')
            vmctl.pointer(VM, 85, 778, 'left')
            own_home_window(restore, 'existing Explorer launched from the real pin')
            pid = user('pgrep -x win7-explorer')
            user(f'touch {TREE}/slow')
            go('LocalA')
            held = lambda: user(f'test -e {TREE}/pending -a -e {TREE}/slow && echo pending', check=False) == 'pending'
            wait_for(held, 'Explorer saved history lookup is pending in the kernel')
            # The second address-bar navigation must complete in the same existing window before release.
            key('LEFTALT', 'D')
            vmctl.type_text(VM, f'{TREE}/LocalB\n')
            shot(out / 'existing-explorer-held.png')
            wait_for(lambda: (explorer() or ('',))[0] == 'LocalB', 'same Explorer can navigate while history is held', timeout=3)
            assert held() and user('pgrep -x win7-explorer') == pid
            shot(out / 'existing-explorer-navigated.png')
            user(f'rm -f {TREE}/slow')
            key('LEFTCTRL', 'W')
            wait_for(lambda: explorer() is None, 'existing Explorer remains closable')
            print('Existing Explorer navigated to a second real folder before the history filesystem lookup returned.')
            return
        unit(restore, f'bash -c "cd {TREE}; exec ./fs -f -o attr_timeout=0,entry_timeout=0,negative_timeout=0 Share"')
        wait_for(lambda: user(f'mountpoint -q {TREE}/Share && echo ready', check=False) == 'ready', 'FUSE test share mounted')
        restore.callback(user, f'fusermount3 -u {TREE}/Share')
        restore.callback(user, f'rm -f {TREE}/slow')
        toggle('windows')
        panel('w.writeConfig("launchers", ["applications:org.win7classic.explorer.desktop"]);')
        vmctl.pointer(VM, 85, 778, 'left')
        own_home_window(restore, 'Explorer launches from the real pin')
        for folder in ('Share/Projects', 'Share/Other', 'Share/Projects'):
            go(folder, caption=folder.split('/')[-1])
        key('LEFTCTRL', 'W')
        wait_for(lambda: explorer() is None, 'training window closed')

        def arm():
            user(f'rm -f {TREE}/pending; touch {TREE}/slow')

        def pending():
            return user(f'test -e {TREE}/pending -a -e {TREE}/slow && echo pending', check=False) == 'pending'

        def unavailable(name, launcher=False):
            image, x, y = popup(out, name, 0, launcher=launcher, unavailable=True)
            assert ocr(out, name, image, (x + 5, y + 3, x + 170, y + 42)) == ['Frequent', 'Frequent', 'unavailable']

        def release():
            user(f'rm -f {TREE}/slow')
            wait_for(lambda: not pending(), 'filesystem request released')
            time.sleep(.6)

        def since():
            return user('date +"%Y-%m-%d %H:%M:%S.%6N"')

        if scenario == 'click-away':
            click_away_while_pending(out, restore, arm, pending, release)
            return

        if scenario == 'initial':
            arm()
            start = since()
            unavailable('delayed-first-query', launcher=True)
            assert pending(), 'the first menu query did not touch the held filesystem'
            assert 'Frequent unavailable: initial check timed out' in user(
                f"journalctl --user -u plasma-plasmashell --since '{start}' --no-pager")
            key('UP'); key('UP'); key('ENTER')
            own_home_window(restore, 'Launch succeeds while first query is still pending')
            assert pending()
            key('LEFTCTRL', 'W')
            wait_for(lambda: explorer() is None, 'launched window closes')
            release()
            popup(out, 'populated-after-first-release', 1, launcher=True)
            key('ESC')
            print('Delayed first query reports unavailability without moving actions; next opening shows real history.')
            return

        _, x, y = popup(out, 'populated-before-slow-poll', 1, launcher=True)
        arm()
        wait_for(pending, 'visible menu poll entered slow VFS lookup', timeout=2)
        wait_for(lambda: dismissed(out, 'poll-dismissed-during-lookup', x, y),
                 'visible menu dismissed before the filesystem responded', timeout=3)
        assert pending()
        unavailable('launch-while-slow', launcher=True)
        key('UP'); key('UP'); key('ENTER')
        own_home_window(restore, 'Launch row activates while filesystem lookup is still stalled')
        assert pending()
        unavailable('unpin-while-slow')
        key('UP'); key('UP'); key('ENTER')
        launchers = lambda: user('grep "^launchers=" ~/.config/plasma-org.kde.plasma.desktop-appletsrc')
        wait_for(lambda: 'org.win7classic.explorer.desktop' not in launchers(), 'Unpin while lookup is stalled')
        unavailable('pin-while-slow')
        key('UP'); key('UP'); key('ENTER')
        wait_for(lambda: 'org.win7classic.explorer.desktop' in launchers(), 'Pin while lookup is stalled')
        unavailable('close-while-slow')
        key('UP'); key('ENTER')
        wait_for(lambda: explorer() is None, 'Close window while lookup is stalled')
        assert pending()
        user(f'rm -f {TREE}/slow')
        time.sleep(.6)
        popup(out, 'populated-after-release', 1, launcher=True)
        key('ESC')
        print('Real Launch, Unpin, Pin and Close completed with the share still held; poll hid the existing rows before release.')


if __name__ == '__main__':
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'poll')
