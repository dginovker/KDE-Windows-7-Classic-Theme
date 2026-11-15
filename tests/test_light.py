#!/usr/bin/env python3
"""Windows mode is fully light even when the current theme is dark (issue #21), in the lab VM.

Current mode is set to Breeze Dark. In Windows mode no dark background may remain in kdeglobals (only Classic's
navy selection), the named color scheme is the Classic one, the desktop portal reports a light preference, and an
inactive Dolphin window's toolbar is drawn light. Switching back restores Breeze Dark exactly.
"""
from pathlib import Path
import sys
import time

from PIL import Image

from lab import VM, vmctl, user, toggle, install, shot, wait_for, kwin_script, windows

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-light-test')
DARK_BACKGROUNDS = r'''python3 - <<'PY'
import re
group, dark = None, []
for line in open('/home/tester/.config/kdeglobals'):
    line = line.strip()
    if line.startswith('['):
        group = line
    m = re.match(r'(Background\w*)=(\d+),(\d+),(\d+)', line)
    if m and group.startswith('[Colors') and group != '[Colors:Selection]' and sum(map(int, m.groups()[1:])) < 300:
        dark.append(f'{group} {m.group(1)}')
print(dark)
PY'''
PORTAL = ('gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop '
          '--method org.freedesktop.portal.Settings.ReadOne org.freedesktop.appearance color-scheme')
COLORS = "sed -n '/^\\[Colors/,/^$/p;/^ColorScheme=/p' ~/.config/kdeglobals | sha256sum"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    user('plasma-apply-colorscheme BreezeDark >/dev/null')
    time.sleep(2)
    dark_colors = user(COLORS)
    assert user(PORTAL) == '(<uint32 1>,)', 'Breeze Dark should make the portal prefer dark'

    toggle('windows')
    assert user(DARK_BACKGROUNDS) == '[]', f'dark colors left in Windows mode: {user(DARK_BACKGROUNDS)}'
    assert user("grep '^ColorScheme=' ~/.config/kdeglobals") == 'ColorScheme=Win7Classic'
    assert user('test -f ~/.local/share/color-schemes/Win7Classic.colors && echo ok') == 'ok', 'Classic color scheme not installed'
    wait_for(lambda: user(PORTAL) == '(<uint32 2>,)', 'the portal reports a light preference')

    # Dolphin behind another window: its toolbar uses the inactive header colors.
    user('mkdir -p ~/Classic-demo; systemd-run --user --collect -q dolphin --new-window ~/Classic-demo')
    wait_for(lambda: 'org.kde.dolphin' in windows(), 'Dolphin window')
    kwin_script('for (const w of workspace.windowList()) if (w.resourceClass == "org.kde.dolphin") '
                '{ w.frameGeometry = {x: 100, y: 100, width: 700, height: 450}; }')
    user('systemd-run --user --collect -q kdialog --msgbox "focus elsewhere"')
    wait_for(lambda: 'org.kde.kdialog' in windows(), 'a second window takes focus')
    kwin_script('for (const w of workspace.windowList()) if (w.resourceClass == "org.kde.kdialog") { w.frameGeometry = {x: 850, y: 100, width: 300, height: 150}; workspace.activeWindow = w; }')
    time.sleep(2)
    shot(OUT / '1-inactive-dolphin.png')
    toolbar = Image.open(OUT / '1-inactive-dolphin.png').convert('RGB').getpixel((450, 135))
    assert sum(toolbar) > 450, f'inactive Dolphin toolbar is dark: {toolbar}'
    print(f'Windows mode: no dark colors, Win7Classic scheme, portal light, inactive toolbar {toolbar}')
    user('pkill -u tester -x dolphin; pkill -u tester -x kdialog; true')

    toggle('current')
    assert user(COLORS) == dark_colors, 'Breeze Dark colors not restored exactly'
    wait_for(lambda: user(PORTAL) == '(<uint32 1>,)', 'the portal prefers dark again')
    print('current mode: Breeze Dark restored exactly, portal dark again')

    # Upgrading in Windows mode: the Windows profile was saved by a version without these keys, and the live
    # session still has Breeze Dark's inactive header and scheme name, as that version left them.
    user("""python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / '.local/state/win7-classic/profiles/windows/keys.json'
data = json.loads(p.read_text())
del data['kdeglobals']['[Colors:Header][Inactive]']
del data['kdeglobals']['[General]']['ColorScheme']
p.write_text(json.dumps(data))
PY""")
    toggle('windows')
    assert user(DARK_BACKGROUNDS) == '[]', 'a Windows profile from an older version brought dark colors back'
    user("kwriteconfig6 --group Colors:Header --group Inactive --key BackgroundNormal 32,35,38; kwriteconfig6 --group General --key ColorScheme BreezeDark")
    toggle('current')
    toggle('windows')
    assert user(DARK_BACKGROUNDS) == '[]', 'switching out and back after upgrading in Windows mode kept dark colors'
    assert user("grep '^ColorScheme=' ~/.config/kdeglobals") == 'ColorScheme=Win7Classic'
    toggle('current')
    assert user(COLORS) == dark_colors, 'Breeze Dark colors not restored after the upgrade round trip'
    user('plasma-apply-colorscheme BreezeLight >/dev/null')  # back to the lab's default for other tests
    print('upgrading with an older Windows profile, in or out of Windows mode, still ends light')
    print('ALL LIGHT CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
