"""Use supported System Tray presentation settings without owning the tray's data."""
from pathlib import Path
import re
import sys

from layout import Layout, replace_layout


DEFAULTS = {'reverseIconOrder': 'true', 'iconSpacing': '1'}
MARKER = 'win7ClassicTrayDefaultsApplied'


def migrate(text):
    layout = Layout(text)
    inserts = {}
    eol = '\r\n' if '\r\n' in text else '\n'

    def add(group, values):
        if not values:
            return
        lines = ''.join(f'{key}={value}{eol}' for key, value in values.items())
        if group in layout.groups:
            start, end = layout.groups[group]
            newline = text.find('\n', start, end)
            if newline == -1:
                inserts.setdefault(end, []).append(eol + lines)
            else:
                inserts.setdefault(newline + 1, []).append(lines)
        else:
            header = ''.join(f'[{part}]' for part in group)
            inserts.setdefault(len(text), []).append(f'{eol}{header}{eol}{lines}')

    for panel in layout.groups:
        if len(panel) != 2 or panel[0] != 'Containments' or layout.get(panel, 'plugin') != 'org.kde.panel':
            continue
        applets = (*panel, 'Applets')
        order = (layout.get((*panel, 'General'), 'AppletOrder') or '').split(';')
        for first, second in zip(order, order[1:]):
            frame, tray = (*applets, first), (*applets, second)
            if (layout.get(frame, 'plugin') != 'org.win7classic.trayframe' or layout.get(frame, MARKER) is not None
                    or layout.get(tray, 'plugin') != 'org.kde.plasma.systemtray'):
                continue
            general = (*tray, 'General')
            # KConfig can qualify keys (e.g. [$i]); those are still explicit choices.
            start, end = layout.groups.get(general, (0, 0))
            keys = set(re.findall(r'(?m)^([^=\[\n]+)(?:\[\$[^\]\n]+\])*=', text[start:end]))
            add(general, {k: v for k, v in DEFAULTS.items() if k not in keys})
            # KDE may remove a key when the user sets it back to its upstream default.
            add(frame, {MARKER: 'true'})

    for offset, values in sorted(inserts.items(), reverse=True):
        text = text[:offset] + ''.join(values) + text[offset:]
    return text


def apply(path):
    original = path.read_bytes()
    text = original.decode('utf-8')
    result = migrate(text)
    if result != text:
        replace_layout(path, original, result)
        print('applied Classic System Tray defaults where no explicit choices were saved')


if __name__ == '__main__':
    try:
        apply(Path(sys.argv[1]))
    except (OSError, ValueError) as error:
        sys.exit(f'System Tray layout migration failed: {error}')
