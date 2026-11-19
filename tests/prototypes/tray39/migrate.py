#!/usr/bin/env python3
"""Build a reversible migration receipt from a staged Windows panel, never current."""
import argparse
from hashlib import sha256
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'toggle/windows'))
from layout import Layout

STOCK = 'org.kde.plasma.systemtray'
CLASSIC = 'org.win7classic.tray'


def transform(text, undo=False):
    layout = Layout(text)
    spans = []
    old, new = (CLASSIC, STOCK) if undo else (STOCK, CLASSIC)
    for group in layout.groups:
        if len(group) != 4 or group[0] != 'Containments' or group[2] != 'Applets':
            continue
        if layout.get(group, 'plugin') != old or layout.get(group[:2], 'plugin') != 'org.kde.panel':
            continue
        order = (layout.get((*group[:2], 'General'), 'AppletOrder') or '').split(';')
        if order.count(group[-1]) != 1 or order.index(group[-1]) == 0:
            continue
        predecessor = order[order.index(group[-1]) - 1]
        if layout.get((*group[:3], predecessor), 'plugin') != 'org.win7classic.trayframe':
            continue
        start, end = layout.groups.get((*group, 'Configuration'), (0, 0))
        if re.search(r'(?m)^SystrayContainmentId(?:\[\$[^\]\n]+\])*=', text[start:end]):
            raise ValueError(f'Legacy separate tray containment needs explicit migration: {group!r}')
        if any('[$i]' in ''.join(f'[{part}]' for part in g) and g[:len(group)] == group for g in layout.groups):
            raise ValueError(f'Immutable tray group requires no migration: {group!r}')
        spans.append(layout.value_span(group, 'plugin'))
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged-windows', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path, help='New scratch directory')
    args = parser.parse_args()
    old = args.staged_windows.read_bytes()
    new = transform(old.decode()).encode()
    if old == new:
        raise SystemExit('No stock tray immediately after a Classic tray frame')
    if transform(new.decode(), undo=True).encode() != old:
        raise SystemExit('Migration is not reversible byte-for-byte')
    args.receipt.mkdir(mode=0o700)
    for name, data in [('original', old), ('converted', new)]:
        (args.receipt / name).write_bytes(data)
        print(f'{sha256(data).hexdigest()}  {name}')


if __name__ == '__main__':
    main()
