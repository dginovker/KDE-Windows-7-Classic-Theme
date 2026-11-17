#!/usr/bin/env python3
"""Issue #29: genuine popup pixels, capability matrix, and real non-destructive session actions."""
import json
from pathlib import Path
import sys
import time
from PIL import Image, ImageChops
from lab import ROOT, VM, vmctl, install, toggle, user, shot, wait_for, windows, kwin_script, kwin_query
from test_startmenu import open_menu, menu_open
from test_lock import locked, type_password, PASSWORD

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-shutdown-menu-test')
BOX = (340, 607, 449, 749)
TOPS = (3, 23, 43, 71, 99, 119)
CAPS = ('canSwitchUser', 'canLogout', 'canLock', 'canReboot', 'canSuspend', 'canHibernate')
GRAY = (128, 128, 128)
CONTROL = '/tmp/shutdown-fixture-control.json'
REPORT = '/tmp/shutdown-fixture-report.json'


def capture(name, park=True):
    if park:
        vmctl.pointer(VM, 640, 790)
    time.sleep(0.3)
    shot(OUT / f'{name}.png')
    return Image.open(OUT / f'{name}.png').convert('RGB').crop(BOX)


def structure(name, image, selected=-1):
    native = Image.open(ROOT / 'reference/screenshots/w7-shutdown-menu.png').convert('RGB').crop(BOX)
    if selected >= 0:
        selected_reference = Image.open(ROOT / 'reference/screenshots/w7-shutdown-menu-selected.png').convert('RGB').crop(BOX)
        native.paste(selected_reference.crop((3, 71, 106, 91)), (3, TOPS[selected]))
    diff = ImageChops.difference(image, native)
    for top in TOPS:
        diff.paste((0, 0, 0), (27, top + 2, 104, top + 18))
    diff.paste((0, 0, 0), (0, 126, 12, 142))  # genuine pointer crossing the lower-left bevel
    image.save(OUT / f'{name}-crop.png')
    diff.point(lambda v: 255 if v else 0).save(OUT / f'{name}-diff.png')
    assert diff.getbbox() is None, f'{name}: structural mismatch {diff.getbbox()}'


def popup_open():
    shot(OUT / 'probe.png')
    image = Image.open(OUT / 'probe.png').convert('RGB')
    return image.getpixel((448, 607)) == (64, 64, 64) and image.getpixel((345, 673)) == GRAY


def open_shutdown():
    open_menu()
    vmctl.pointer(VM, 335, 735, 'left')
    wait_for(popup_open, 'shutdown popup at the native position')


def fixture_state():
    return json.loads(user(f'cat {REPORT}'))


def set_fixture(capabilities, ready=True, switch_user=True):
    data = json.dumps({'capabilities': capabilities, 'ready': ready, 'switchUserSupported': switch_user, 'open': True, 'nonce': time.monotonic_ns()})
    user(f"printf '%s' '{data}' > {CONTROL}")
    wait_for(lambda: fixture_state()['visible'] and fixture_state()['current'] == -1, 'fixture open')
    kwin_script('for (const w of workspace.windowList()) if(w.caption=="fixture_shutdown_menu.py") '
                '{w.frameGeometry={x:340,y:607,width:109,height:142};workspace.activeWindow=w;}')


def matrix():
    vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_shutdown_menu.py'), '/tmp/fixture_shutdown_menu.py')
    vmctl.run(VM, 'chmod 644 /tmp/fixture_shutdown_menu.py', 10)
    enabled = dict.fromkeys(CAPS, True)
    user(f"echo '{json.dumps({'capabilities': enabled, 'ready': True})}' > {CONTROL}; rm -f {REPORT}; "
         'systemd-run --user --collect -q python3 /tmp/fixture_shutdown_menu.py')
    try:
        wait_for(lambda: 'python3' in windows(), 'shutdown fixture window')
        kwin_script('for (const w of workspace.windowList()) if(w.caption=="Shutdown menu fixture") '
                    '{w.frameGeometry={x:329,y:723,width:14,height:23};workspace.activeWindow=w;}')
        set_fixture(enabled)
        wait_for(popup_open, 'fixture popup')
        structure('matrix-enabled', capture('matrix-enabled'))
        for index, capability in enumerate(CAPS):
            vmctl.pointer(VM, 440, BOX[1] + TOPS[index] + 10)
            time.sleep(0.2)
            structure(f'hover-{capability}', capture(f'hover-{capability}', park=False), index)
        for index, capability in enumerate(CAPS):
            disabled = enabled | {capability: False}
            set_fixture(disabled)
            image = capture(f'disabled-{capability}')
            structure(f'disabled-{capability}', image)
            text = image.crop((27, TOPS[index] + 2, 103, TOPS[index] + 18))
            colors = list(text.get_flattened_data())
            assert min(min(c) for c in colors) >= 128 and any(max(c) > 240 for c in colors), f'{capability}: no embossed disabled text'
            vmctl.pointer(VM, 440, BOX[1] + TOPS[index] + 10, 'left')
            assert fixture_state()['visible'] and fixture_state()['chosen'] == -1, f'{capability}: disabled action triggered'
            vmctl.keys(VM, 'KEY_HOME')  # unused key must not activate anything
            vmctl.keys(VM, 'KEY_DOWN')
            expected = 1 if index == 0 or index == 2 else 0  # switching user also requires locking
            wait_for(lambda: fixture_state()['current'] == expected, 'keyboard skips unavailable item')
            vmctl.keys(VM, 'KEY_ENTER')
            wait_for(lambda: fixture_state()['chosen'] == expected, 'enabled keyboard action')
        set_fixture(enabled, switch_user=False)
        vmctl.pointer(VM, 440, 620, 'left')
        assert fixture_state()['visible'] and fixture_state()['chosen'] == -1, 'unsupported display manager allowed switching users'
        vmctl.keys(VM, 'KEY_DOWN')
        wait_for(lambda: fixture_state()['current'] == 1, 'unsupported seat skipped')
        set_fixture(enabled, ready=False)
        structure('loading', capture('loading'))
        vmctl.keys(VM, 'KEY_DOWN')
        vmctl.keys(VM, 'KEY_ENTER')
        assert fixture_state()['visible'] and fixture_state()['chosen'] == -1, 'loading backend accepted an action'
        set_fixture(dict.fromkeys(CAPS, False))
        vmctl.keys(VM, 'KEY_UP')
        vmctl.keys(VM, 'KEY_ENTER')
        assert fixture_state()['visible'] and fixture_state()['chosen'] == -1, 'all-disabled backend accepted an action'
        print('all enabled/disabled/hover rows, loading, all-disabled, keyboard skip and activation passed')
    finally:
        user('pkill -f "^/usr/bin/python3 /tmp/fixture_shutdown_menu.py"; true')


def denied_power_action():
    source = ROOT / 'plasma/org.win7classic.taskbar/contents/ui/StartMenu.qml'
    installed = '/home/tester/.local/share/plasma/plasmoids/org.win7classic.taskbar/contents/ui/StartMenu.qml'
    original = source.read_text()
    instrumented = original.replace('powerAction("Suspend",', 'powerAction("Issue29DeniedSuspend",')
    assert instrumented != original, 'failure injection did not match the production call'
    injection = OUT / 'suspend-denied.qml'
    injection.write_text(instrumented)
    try:
        vmctl.transfer(VM, 'put', str(injection), installed)
        toggle('current')
        toggle('windows')
        open_shutdown()
        vmctl.pointer(VM, 400, 716, 'left')
        def error_visible():
            return any(row[0] == 'Sleep' for row in kwin_query('for(const w of workspace.windowList()) emit(w.caption);'))
        wait_for(error_visible, 'Classic Sleep error message box')
        shot(OUT / 'suspend-error.png')
        journal = user('journalctl --user -u plasma-plasmashell --since -1min --no-pager -o cat')
        assert 'Sleep failed.' in journal and 'org.freedesktop.DBus.Error.AccessDenied' in journal and 'Issue29DeniedSuspend' in journal, journal
        (OUT / 'suspend-error.log').write_text(journal)
        vmctl.keys(VM, 'KEY_ESC')
        wait_for(lambda: not error_visible(), 'error message dismissed')
        print('injected logind failure displays a Classic error message and journals the action/error; no silent failure')
    finally:
        vmctl.transfer(VM, 'put', str(source), installed)
        toggle('current')
        toggle('windows')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    toggle('windows')
    open_shutdown()
    structure('live', capture('live'))
    vmctl.keys(VM, 'KEY_ESC')
    assert menu_open(), 'Esc closed Start instead of returning from the submenu'
    vmctl.keys(VM, 'KEY_RIGHT')
    wait_for(popup_open, 'keyboard reopens submenu')
    vmctl.keys(VM, 'KEY_LEFT')
    assert menu_open(), 'Left did not return to Start'
    vmctl.keys(VM, 'KEY_ESC')
    open_shutdown()
    vmctl.pointer(VM, 800, 700, 'left')
    wait_for(lambda: not menu_open(), 'outside click dismisses both menus')

    capabilities = user('for method in CanReboot CanSuspend CanHibernate; do '
                        'printf "%s=" "$method"; qdbus6 --system org.freedesktop.login1 /org/freedesktop/login1 '
                        'org.freedesktop.login1.Manager.$method; done; cat /proc/swaps')
    (OUT / 'capabilities.txt').write_text(capabilities + '\n')
    assert 'CanHibernate=na' in capabilities or 'CanHibernate=no' in capabilities, capabilities
    open_shutdown()
    live = capture('live-gated')
    assert min(min(c) for c in live.crop((27, 121, 103, 137)).get_flattened_data()) >= 128, 'unsupported Hibernate is enabled'
    vmctl.pointer(VM, 440, 736, 'left')
    assert popup_open(), 'unsupported Hibernate activated'
    vmctl.keys(VM, 'KEY_ESC')
    vmctl.keys(VM, 'KEY_ESC')
    matrix()

    # Deliberately turn KDE's normal confirmation preference OFF: these actions must still prompt.
    confirm_present = user('if test -e ~/.config/ksmserverrc; then '
                           'cp -p ~/.config/ksmserverrc /tmp/issue29-ksmserverrc && echo yes; else echo no; fi')
    confirm_before = user('sha256sum ~/.config/ksmserverrc 2>/dev/null || echo absent')
    try:
        user('kwriteconfig6 --file ksmserverrc --group General --key confirmLogout false && '
             'systemd-run --user --collect -q kate --new /tmp/shutdown-unsaved.txt')
        wait_for(lambda: 'org.kde.kate' in windows(), 'Kate unsaved-work probe')
        vmctl.type_text(VM, 'UNSAVED issue 29 session preservation')
        before = user('pgrep -x kwin_wayland; pgrep -x plasmashell; pgrep -x kate')
        caption = windows()['org.kde.kate'][0]
        assert '*' in caption, f'Kate probe is not modified: {caption}'
        for name, y in [('restart', 688), ('logoff', 640)]:
            open_shutdown()
            vmctl.pointer(VM, 400, y, 'left')
            try:
                wait_for(lambda: user('pgrep -f "^/usr/lib/ksmserver-logout-greeter"', check=False) != '', f'{name} KDE confirmation', 10)
                shot(OUT / f'{name}-confirmation.png')
            finally:
                # KDE counts down; never spend time reviewing the image while the prompt is armed.
                vmctl.keys(VM, 'KEY_ESC')
            wait_for(lambda: not any('logout' in c.lower() for c in windows()), f'{name} cancelled')
            assert user('pgrep -x kwin_wayland; pgrep -x plasmashell; pgrep -x kate') == before, f'{name} replaced session processes'
            assert windows()['org.kde.kate'][0] == caption, f'{name} lost the unsaved Kate document'
        open_shutdown()
        vmctl.pointer(VM, 400, 660, 'left')
        wait_for(locked, 'Lock action locks the session')
        time.sleep(2)
        vmctl.pointer(VM, 610, 430)
        time.sleep(1)
        shot(OUT / 'locked.png')
        type_password(PASSWORD)
        wait_for(lambda: not locked(), 'tester password unlocks', 20)
        assert user('pgrep -x kwin_wayland; pgrep -x plasmashell; pgrep -x kate') == before
        print('Restart and Log off force KDE confirmation with confirmLogout=false; Cancel preserves unsaved Kate and session PIDs; Lock/password unlock passed')
    finally:
        if confirm_present == 'yes':
            user('cp -p /tmp/issue29-ksmserverrc ~/.config/ksmserverrc && rm /tmp/issue29-ksmserverrc')
        else:
            user('rm -f ~/.config/ksmserverrc')
        user('pkill -KILL -u tester -x kate; true')
        assert user('sha256sum ~/.config/ksmserverrc 2>/dev/null || echo absent') == confirm_before, 'confirmation preference presence/value changed'
    denied_power_action()
    toggle('current')
    print('ALL SHUTDOWN MENU CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
