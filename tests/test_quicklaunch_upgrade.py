#!/usr/bin/env python3
"""Legacy saved Windows Quick Launch migration: genuine VM UI, rollback and live work preservation."""
import json
from pathlib import Path
import shlex
import sys
import time

from lab import ROOT, VM, activate, digest, install, shot, toggle, user, vmctl, wait_for, windows
from test_quicklaunch_migration import FIXTURE, migration

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-quicklaunch-upgrade')
STATE = '~/.local/state/win7-classic'
SAVED = STATE + '/profiles/windows'
NAME = 'plasma-org.kde.plasma.desktop-appletsrc'
HELPER = '~/.local/share/win7-classic/windows/migrate-quicklaunch'
SHELL = 'qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript'
LATEST = 'applications:org.win7classic.explorer.desktop,applications:org.kde.konsole.desktop,applications:firefox.desktop'
TEXT = 'unsaved work across Quick Launch migration'


def shell(script):
    return user(SHELL + ' ' + shlex.quote(script))


def get(remote, name):
    path = OUT / name
    vmctl.transfer(VM, 'get', str(path), remote.replace('~', '/home/tester'))
    return path.read_bytes()


def profile_digest(directory):
    return user(f'cd {directory} && find . -type f -print0 | sort -z | xargs -0 sha256sum')


def alive(pids):
    assert user('pgrep -u tester -x kwin_wayland; pgrep -u tester -x kate') == pids, 'KWin or unsaved app restarted'
    assert '*' in windows()['org.kde.kate'][0], 'unsaved Kate buffer lost'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    for name in ('metadata.json', 'contents/config/main.xml', 'contents/ui/main.qml'):
        vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_widget' / name), f'/tmp/quicklaunch-{name.replace("/", "-")}')
    user('d=~/.local/share/plasma/plasmoids/local.win7test.note; mkdir -p $d/contents/{ui,config}; '
         'cp /tmp/quicklaunch-metadata.json $d/metadata.json; '
         'cp /tmp/quicklaunch-contents-config-main.xml $d/contents/config/main.xml; '
         'cp /tmp/quicklaunch-contents-ui-main.qml $d/contents/ui/main.qml; '
         'systemctl --user reset-failed plasma-plasmashell; systemctl --user restart plasma-plasmashell')
    time.sleep(3)
    toggle('windows')
    toggle('current')
    old = get(SAVED + '/' + NAME, 'fresh-saved-appletsrc').decode()
    layout = migration.Layout(old)
    desktop_ids = {g[1] for g in layout.groups if len(g) == 2 and layout.get(g, 'plugin') in ('org.kde.plasma.folder', 'org.kde.desktopcontainment')}
    desktop = ''.join(old[start:end] for g, (start, end) in layout.groups.items() if len(g) >= 2 and g[0] == 'Containments' and g[1] in desktop_ids)
    legacy = OUT / 'legacy-input-appletsrc'
    legacy.write_text(desktop + FIXTURE.read_text())
    vmctl.transfer(VM, 'put', str(legacy), '/home/tester/.local/state/win7-classic/profiles/windows/' + NAME)
    user(f'kwriteconfig6 --file {SAVED}/plasmashellrc --group PlasmaViews --group "Panel 26" --key floating false; '
         f'kwriteconfig6 --file {SAVED}/plasmashellrc --group PlasmaViews --group "Panel 26" --group Defaults --key thickness 44; '
         f'cp {HELPER} {HELPER}.real; printf "#!/bin/sh\\nexit 0\\n" >{HELPER}')
    toggle('windows')
    time.sleep(2)
    assert 'org.kde.plasma.quicklaunch' in shell('print(panels()[0].widgets().map(w=>w.type).join(","))')
    shell('for(const p of panels()) for(const w of p.widgets()) if(w.type=="org.win7classic.taskbar") '
          '{ w.currentConfigGroup=["General"]; w.writeConfig("launchers", ' + json.dumps(LATEST.split(',')) + '); }')
    user('rm -f /tmp/quicklaunch-work-proof.txt; systemd-run --user --collect -q kate -n')
    wait_for(lambda: 'org.kde.kate' in windows(), 'Kate')
    activate('org.kde.kate')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_N')
    vmctl.type_text(VM, TEXT)
    pids = user('pgrep -u tester -x kwin_wayland; pgrep -u tester -x kate')
    shot(OUT / '1-legacy-quicklaunch-red.png')
    toggle('current')
    time.sleep(2)
    healthy = digest()
    current_profile = profile_digest(STATE + '/profiles/current')
    original_windows = profile_digest(SAVED)
    original = get(SAVED + '/' + NAME, 'latest-live-windows-appletsrc')
    assert ('launchers=' + LATEST).encode() in original, 'latest live pins were not saved'
    expected, panels = migration.migrate(original.decode())
    assert panels == ['26']

    for diagnostic in ('echo injected-migration-failure >&2\n', ''):
        user(f'printf %s {shlex.quote("#!/bin/sh\n" + diagnostic + "exit 42\n")} >{HELPER}')
        log = toggle('windows', expect_ok=False)
        assert '(exit 42)' in log and 'rolling back to current' in log, log
        assert not diagnostic or 'injected-migration-failure' in log, log
        assert digest() == healthy and profile_digest(SAVED) == original_windows
        assert profile_digest(STATE + '/profiles/current') == current_profile
        alive(pids)
    print('diagnostic and silent exit 42 both roll back; profiles byte-identical, unsaved work alive')

    real = HELPER.replace('~', '$HOME') + '.real "$@"\n'
    for status, failure in ((42, 'exit 42'), (143, 'kill -TERM $$')):
        wrapper = '#!/bin/bash\nset -e\n' + real + 'if [[ $1 != --check ]]; then\ncp "$1" /tmp/quicklaunch-staged\n' + failure + '\nfi\n'
        user(f'printf %s {shlex.quote(wrapper)} >{HELPER}')
        log = toggle('windows', expect_ok=False)
        assert f'(exit {status})' in log and 'rolling back to current' in log, log
        assert get('/tmp/quicklaunch-staged', f'failed-after-replace-{status}-appletsrc') == expected.encode()
        backups = user(f'find {STATE}/profiles -maxdepth 1 -type d -name "windows-before-quicklaunch.*"').splitlines()
        assert any(profile_digest(path) == original_windows for path in backups), 'recovery missing after replacement failure'
        assert digest() == healthy and profile_digest(SAVED) == original_windows
        assert profile_digest(STATE + '/profiles/current') == current_profile
        alive(pids)
    print('exit 42 and SIGTERM after atomic replacement roll back with exact original recovery already present')

    # Capture exactly what the real helper wrote, before Plasma can persist its own runtime metadata.
    wrapper = '#!/bin/bash\nset -e\n' + real + 'if [[ $1 != --check ]]; then cp "$1" /tmp/quicklaunch-staged; fi\n'
    user(f'printf %s {shlex.quote(wrapper)} >{HELPER}')
    user(f"sed -i 's/plugin=local.win7test.note/plugin=org.example.missing/' {SAVED}/{NAME}")
    invalid_windows = profile_digest(SAVED)
    log = toggle('windows', expect_ok=False)
    assert 'unknown widgets: org.example.missing' in log, log
    assert digest() == healthy and profile_digest(SAVED) == invalid_windows
    assert profile_digest(STATE + '/profiles/current') == current_profile
    alive(pids)
    user(f"sed -i 's/plugin=org.example.missing/plugin=local.win7test.note/' {SAVED}/{NAME}")
    assert profile_digest(SAVED) == original_windows
    print('post-migration widget failure rolls back without committing the staged Windows layout')

    toggle('windows')
    staged = get('/tmp/quicklaunch-staged', 'validated-migration-appletsrc')
    assert staged == expected.encode(), 'unrelated config bytes changed in migration'
    assert (LATEST + ',applications:org.kde.kate.desktop').encode() in staged
    assert 'org.kde.plasma.quicklaunch' not in shell('print(panels()[0].widgets().map(w=>w.type).join(","))')
    backups = user(f'find {STATE}/profiles -maxdepth 1 -type d -name "windows-before-quicklaunch.*" | sort').splitlines()
    assert any(profile_digest(path) == original_windows for path in backups), 'exact original profile recovery copy missing'
    alive(pids)
    shot(OUT / '2-migrated-quicklaunch-green.png')
    user(f'cp {HELPER}.real {HELPER}; rm {HELPER}.real')
    toggle('current')
    assert digest() == healthy and profile_digest(STATE + '/profiles/current') == current_profile
    settled = profile_digest(SAVED)
    for cycle in range(3):
        toggle('windows')
        alive(pids)
        toggle('current')
        assert digest() == healthy and profile_digest(STATE + '/profiles/current') == current_profile
        assert profile_digest(SAVED) == settled, 'repeated migration/save is not byte-identical'
    assert user(f'find {STATE}/profiles -maxdepth 1 -type d -name "windows-before-quicklaunch.*" | sort').splitlines() == backups
    print('exact staged byte preservation, original recovery copy, 3 idempotent live round trips, latest pins and popup pins merged')

    activate('org.kde.kate')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_LEFTSHIFT', 'KEY_S')
    time.sleep(2)
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_A')
    vmctl.type_text(VM, '/tmp/quicklaunch-work-proof.txt\n')
    wait_for(lambda: user('cat /tmp/quicklaunch-work-proof.txt', check=False) == TEXT, 'exact unsaved work saved after migration')
    (OUT / 'switch.log').write_text(user(f'cat {STATE}/switch.log'))
    print('ALL QUICK LAUNCH UPGRADE CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
