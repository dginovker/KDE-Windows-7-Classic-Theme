#!/usr/bin/env python3
"""Compare mapped Classic Network popups with the standalone Plasma AppletPopup."""
import argparse
import difflib
import json
import re
import shlex
from pathlib import Path

from lab import VM, kwin_query, shot, toggle, user, vmctl, wait_for
from test_tray_popup_sizes import LIVE, NAME, NETWORK, SAVED, STATE, groups, install, key, network_cell, popup, raw, settings


def shell(js):
    return user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript ' + shlex.quote(js))


def configure(path, group, width, height):
    args = ' '.join('--group ' + shlex.quote(x.decode()) for x in re.findall(rb'\[([^]]+)\]', group))
    user(f'set -eu; kwriteconfig6 --file {path} {args} --key popupWidth {width}; '
         f'kwriteconfig6 --file {path} {args} --key popupHeight {height}')


def restart():
    user('systemctl --user reset-failed plasma-plasmashell; systemctl --user start plasma-plasmashell')
    wait_for(lambda: shell('print(panels().length)').isdigit(), 'Plasma panels', timeout=30)


def sample(out, point, group, scale, action):
    assert popup() is None
    before_layout = raw(LIVE)
    before = groups(before_layout)[group]
    vmctl.pointer(VM, *point, 'left')
    wait_for(popup, 'real Network AppletPopup')
    initial = popup()
    shot(out / 'opened.png')
    x, y, w, h = initial
    # The panel-facing edges are not resizable.
    # At fractional scale the rounded corner can miss the Wayland input region.
    edge = (x + 2, y + (2 if scale == 1 else h/2))
    edge = tuple(round(v * scale) for v in edge)
    print(f'{out.name} initial rect {initial}; physical resize edge {edge}', flush=True)
    vmctl.pointer(VM, *edge)

    def resizing():
        return kwin_query('for (const w of workspace.windowList()) if (w.resourceClass === "org.kde.plasmashell" && '
                          'w.caption === "plasmashell" && !w.popupWindow && !w.notification) emit(w.resize);') == [['true']]

    if action == 'cancel':
        vmctl.button(VM, 'left', True)
        try:
            for d in (12, 30, 50):
                vmctl.pointer(VM, edge[0] - round(d * scale), edge[1] - (d if scale == 1 else 0))
            def is_resized():
                g = popup()
                return g and g[2] > w + 40 and resizing()
            wait_for(is_resized, 'KWin resizes with left button still held')
            shot(out / 'held.png')
            key('ESC')
            wait_for(lambda: popup() == initial, 'Escape restores the exact KWin rect before button release')
        finally:
            vmctl.button(VM, 'left', False)
        assert popup() == initial
    else:
        vmctl.button(VM, 'left', True)
        try:
            wait_for(resizing, 'KWin acknowledges edge press without pointer motion')
        finally:
            vmctl.button(VM, 'left', False)
        assert not resizing() and popup() == initial, 'an edge click without motion must not resize the popup'
        new_scale = 1.5 if scale == 1 else 2
        user(f'kscreen-doctor output.1.scale.{new_scale}')
        wait_for(lambda: json.loads(user('kscreen-doctor -j'))['outputs'][0]['scale'] == new_scale,
                 'live output scale changes while the popup stays mapped')
        def clamped():
            g = popup()
            return g and g[2] < w - 50
        wait_for(clamped, 'the still-mapped popup width actually clamps after the live scale change')
    final = popup()
    shot(out / 'after-action.png')
    assert groups(raw(LIVE))[group] == before, 'save must happen on dismissal, not during the action'
    key('ESC')
    wait_for(lambda: popup() is None, 'Escape dismisses the mapped popup')
    after_layout = raw(LIVE)
    after = groups(after_layout)[group]
    delta = b''.join(difflib.diff_bytes(difflib.unified_diff, before.splitlines(True), after.splitlines(True),
                                       b'before', b'after'))
    (out / 'before.ini').write_bytes(before_layout)
    (out / 'after.ini').write_bytes(after_layout)
    (out / 'applet.diff').write_bytes(delta)
    print(f'{out.name} {action} at {scale}: {initial} → {final}; applet delta {delta!r}', flush=True)
    return initial, final, before, after


def main(out, target, scale, action):
    out.mkdir(parents=True, exist_ok=True)
    assert user('/usr/bin/win7-classic status') == 'current'
    install(target)
    backup = '~/.local/state/w62-parity-backup'
    user(f'set -eu; mkdir {backup}; cp -a {STATE} {LIVE} ~/.config/plasmashellrc {backup}/; '
         f'kscreen-doctor output.1.scale.{scale}')
    try:
        classic_group, _ = settings(raw(SAVED), NETWORK)
        id_ = shell('const p = panels()[0]; for (const w of p.widgets()) w.remove(); '
                    'p.location="bottom"; p.height=44; p.floating=false; '
                    'p.addWidget("org.kde.plasma.panelspacer"); '
                    'print(p.addWidget("org.kde.plasma.networkmanagement").id);')
        assert id_.isdigit(), id_

        def standalone_group():
            return next((k + b'[Configuration]' for k, v in groups(raw(LIVE)).items()
                         if re.fullmatch(rb'\[Containments\]\[\d+\]\[Applets\]\[' + id_.encode() + rb'\]', k)
                         and b'plugin=' + NETWORK in v.splitlines()), None)

        wait_for(standalone_group, 'standalone Network applet saved')
        current_group = standalone_group()
        user('systemctl --user stop plasma-plasmashell')
        # Width rather than height isolates the shared screen limit from the panels' different reservations.
        width = (1100 if scale == 1 else 780) if action == 'edge-scale' else 393
        configure(LIVE, current_group, width, 380)
        configure(SAVED, classic_group, width, 380)
        restart()
        for name in ('current-standalone', 'classic-hosted'):
            (out / name).mkdir()
        shot(out / 'current-panel.png')
        current = sample(out / 'current-standalone', (1280 - round(24 * scale), 800 - round(22 * scale)), current_group, scale, action)
        user(f'kscreen-doctor output.1.scale.{scale}')
        toggle('windows', packaged=True)
        point = network_cell(out, scale)
        classic = sample(out / 'classic-hosted', point, classic_group, scale, action)
        user(f'kscreen-doctor output.1.scale.{scale}')
        toggle('current', packaged=True)
        assert groups(raw(SAVED))[classic_group] == classic[-1], 'live geometry bytes survive saving the Windows profile'
        assert classic == current, (classic, current)
        if action == 'edge-scale':
            assert current[-1] != current[-2], 'the native clamp should persist on dismissal'
        print(f'PASS {scale} {action}: mapped KWin rectangles and exact per-applet INI bytes match standalone Plasma')
    finally:
        if user('/usr/bin/win7-classic status') == 'windows':
            toggle('current', packaged=True)
        user(f'set -eu; kscreen-doctor output.1.scale.1; systemctl --user stop plasma-plasmashell; '
             f'rm -rf {STATE}; mv {backup}/win7-classic {STATE}; mv {backup}/{NAME} {backup}/plasmashellrc ~/.config/; rmdir {backup}')
        restart()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), required=True)
    parser.add_argument('--action', choices=('cancel', 'edge-scale'), required=True)
    args = parser.parse_args()
    main(args.outdir, args.target, args.scale, args.action)
