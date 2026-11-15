#!/usr/bin/env python3
"""Current-mode widgets carried into Windows mode (issue #14), run from the host against the lab VM.

Current mode gets a second virtual desktop, a configured pager and a custom widget with a setting. On the first
switch they must appear in the Classic taskbar with byte-identical config groups, the pager must switch desktops,
and switching back must restore current mode exactly. `win7-classic rebuild` must pick up later changes.
"""
from pathlib import Path
import re
import sys
import time

from importlib.machinery import SourceFileLoader

from PIL import Image

from lab import ROOT, VM, vmctl, user, toggle, digest, install, shot, wait_for

seed = SourceFileLoader('seed', str(ROOT / 'toggle/windows/seed')).load_module()
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-widgets-test')
APPLETSRC = '~/.config/plasma-org.kde.plasma.desktop-appletsrc'
SHELL = 'qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript'
MAGENTA = (255, 0, 255)


def widget_groups(text, plugin):
    """The config groups of the panel widget with this plugin, as {group suffix: lines}."""
    groups, current = {}, None
    for line in text.splitlines():
        if line.startswith('['):
            current = line
            groups[current] = []
        elif current and line.strip():
            groups[current].append(line)
    applet = next(re.match(r'(\[Containments\]\[\d+\]\[Applets\]\[\d+\])', g).group(1) for g, lines in groups.items()
                  if f'plugin={plugin}' in lines and re.fullmatch(r'\[Containments\]\[\d+\]\[Applets\]\[\d+\]', g))
    return {g[len(applet):]: lines for g, lines in groups.items() if g.startswith(applet)}


def panel_types():
    """Plugins of the Classic taskbar panel's widgets in on-screen order (scripting's widgets() is creation order)."""
    Path('/tmp/win7-appletsrc').write_text(user(f'cat {APPLETSRC}'))
    config = seed.Config(Path('/tmp/win7-appletsrc'))
    for group, _ in config.groups:
        if len(group) == 2 and config.get(group, 'plugin') == 'org.kde.panel':
            order = config.get((*group, 'General'), 'AppletOrder')
            return [config.get((*group, 'Applets', a), 'plugin') for a in order.split(';')]
    raise AssertionError('no panel in appletsrc')


def current_desktop():
    return user('qdbus6 org.kde.KWin /KWin org.kde.KWin.currentDesktop')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    # A fresh tester account: this test edits the current-mode panel, so leftovers from earlier runs would pile up.
    code, out, err = vmctl.run(VM, (ROOT / 'vm/prepare-tester.sh').read_text(), 300)
    assert code == 0, out + err
    vmctl.start(VM)
    time.sleep(5)
    install()
    for name in ('metadata.json', 'contents/config/main.xml', 'contents/ui/main.qml'):
        vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_widget' / name), f'/tmp/note-{name.replace("/", "-")}')
    user('d=~/.local/share/plasma/plasmoids/local.win7test.note; rm -rf $d; mkdir -p $d/contents/ui $d/contents/config; '
         'cp /tmp/note-metadata.json $d/metadata.json; cp /tmp/note-contents-config-main.xml $d/contents/config/main.xml; '
         'cp /tmp/note-contents-ui-main.qml $d/contents/ui/main.qml; '
         'systemctl --user reset-failed plasma-plasmashell; systemctl --user restart plasma-plasmashell; sleep 4')
    if user('qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.count') == '1':
        user('qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.createDesktop 1 Two')
    user(f'{SHELL} "const p = panels()[0];'
         ' const n = p.addWidget(\\"local.win7test.note\\"); n.currentConfigGroup = [\\"General\\"]; n.writeConfig(\\"text\\", \\"kept-123\\");'
         ' for (const w of p.widgets()) if (w.type == \\"org.kde.plasma.pager\\") { w.currentConfigGroup = [\\"General\\"]; w.writeConfig(\\"displayedText\\", 0); }"')
    time.sleep(2)
    user('qdbus6 org.kde.KWin /KWin org.kde.KWin.setCurrentDesktop 1')
    before = user(f'cat {APPLETSRC}')
    before_digest = digest()
    shot(OUT / '1-current.png')

    toggle('windows')
    time.sleep(2)
    types = panel_types()
    expected = ['org.win7classic.taskbar', 'org.kde.plasma.pager', 'local.win7test.note', 'org.win7classic.trayframe',
                'org.kde.plasma.systemtray', 'org.win7classic.clock']
    assert types == expected, f'Windows taskbar widgets {types}, expected {expected}'
    after = user(f'cat {APPLETSRC}')
    for plugin in ('org.kde.plasma.pager', 'local.win7test.note', 'org.kde.plasma.systemtray'):
        assert widget_groups(after, plugin) == widget_groups(before, plugin), f'{plugin} config changed'
    print('pager, custom widget and tray carried over with byte-identical config, before the notification area')

    vmctl.pointer(VM, 640, 600)
    time.sleep(1)
    shot(OUT / '2-windows.png')
    image = Image.open(OUT / '2-windows.png').convert('RGB')
    magenta = [x for x in range(1280) if image.getpixel((x, 778)) == MAGENTA]
    assert magenta, 'custom widget not visible on the taskbar'
    vmctl.pointer(VM, magenta[0] - 8, 778, 'left')  # right-hand cell of the pager: desktop 2
    wait_for(lambda: current_desktop() == '2', 'pager switches to desktop 2')
    vmctl.pointer(VM, 640, 600)
    time.sleep(1)
    shot(OUT / '3-desktop-2.png')
    user('qdbus6 org.kde.KWin /KWin org.kde.KWin.setCurrentDesktop 1')
    print('pager switches virtual desktops')

    toggle('current')
    assert digest() == before_digest, 'current mode not restored exactly'
    print('current mode restored exactly')

    # A widget added in current mode later reaches Windows mode only through rebuild.
    user(f'{SHELL} "panels()[0].addWidget(\\"org.kde.plasma.trash\\")"')
    time.sleep(1)
    toggle('windows')
    assert 'org.kde.plasma.trash' not in panel_types(), 'saved Windows layout should be reused as-is'
    code, _, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- ~tester/.local/bin/win7-classic rebuild', 300)
    assert code == 0, err
    assert 'org.kde.plasma.trash' in panel_types(), 'rebuild did not pick up the new current-mode widget'
    print('win7-classic rebuild carries later current-mode changes over')

    toggle('current')
    # Leave a pristine account (one desktop, stock panel) for the other tests.
    code, out, err = vmctl.run(VM, (ROOT / 'vm/prepare-tester.sh').read_text(), 300)
    assert code == 0, out + err
    print('ALL WIDGET CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
