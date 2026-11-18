#!/usr/bin/env python3
"""Real local-file drag to a network-isolated Electron 39, with Dolphin and two target backends."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

from PIL import Image

from lab import ROOT, VM, install, kwin_query, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER

FILE = 'probe space.txt'
PAYLOAD = b'Only synthetic data.\n'
PAYLOAD_HASH = sha256(PAYLOAD).hexdigest()
ELECTRON = '/usr/lib/electron39/electron'


def drag(start, path, cancel=False):
    vmctl.pointer(VM, *start)
    vmctl.button(VM, 'left', True)
    try:
        for pos in path:
            vmctl.pointer(VM, *pos)
            time.sleep(.2)
        if cancel:
            vmctl.keys(VM, 'KEY_ESC')
    finally:
        vmctl.button(VM, 'left', False)
    time.sleep(.7)


def place(title, geometry):
    kwin_script(f'for (const w of workspace.windowList()) if (w.caption === {json.dumps(title)}) {{ '
                f'w.frameGeometry = {geometry}; workspace.activeWindow = w; }}')


def system(script):
    code, out, err = vmctl.run(VM, script, 30)
    assert code == 0, f'{script}: {out}{err}'
    return out.strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('out', type=Path)
    p.add_argument('--installed', action='store_true', help='use currently installed Explorer in Windows mode')
    p.add_argument('--backend', choices=['wayland', 'x11'], action='append')
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    if not args.installed:
        install()
        toggle('windows')
    root = user('mktemp -d /tmp/w7-drag.XXXXXXXX')
    user(f'mkdir {root}/source; printf "Only synthetic data.\\n" > "{root}/source/{FILE}"; test -x {ELECTRON}')
    for fixture in (ROOT / 'tests/fixtures/electron-drop').iterdir():
        vmctl.transfer(VM, 'put', str(fixture), f'{root}/{fixture.name}')
        user(f'test -r {root}/{fixture.name}')
    failures = []
    try:
        for backend in args.backend or ['wayland', 'x11']:
            unit = f'{Path(root).name}-{backend}'
            target = f'Drop probe {unit}'
            source = f'source-{unit}'
            user(f'cp -r {root}/source {root}/{source}')
            env = user("systemctl --user show-environment | grep -E '^(XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|DISPLAY|WAYLAND_DISPLAY|XAUTHORITY)='")
            env = ' '.join('--setenv=' + shlex.quote(line) for line in env.splitlines())
            # A guest system unit owns the isolated network and can reliably reap Chromium's subprocesses.
            user(f': > {root}/{backend}-target.log')
            system(f'systemd-run --collect -q --unit={unit} -p User=tester -p PrivateNetwork=yes -p TimeoutStopSec=3s '
                   f'-p StandardOutput=append:{root}/{backend}-target.log {env} '
                   f'{ELECTRON} --disable-gpu --ozone-platform={backend} {root}/main.js {root} {shlex.quote(target)}')
            units = []
            try:
                def windows():
                    return kwin_query('for (const w of workspace.windowList()) emit(w.caption, w.resourceClass);')

                wait_for(lambda: any(r[0] == target for r in windows()), f'{backend} Electron window')
                def is_x11(title):
                    return f'"{title}"' in user('systemd-run --user --pipe --wait --collect -q xwininfo -root -tree')

                assert is_x11(target) == (backend == 'x11')
                pid = system(f'systemctl show -p MainPID --value {unit}')
                user(f'test "$(readlink /proc/{pid}/ns/net)" != "$(readlink /proc/self/ns/net)" && '
                     f'test "$(wc -l </proc/{pid}/net/dev)" = 3 && ! grep -q ^00000000 /proc/{pid}/net/route')
                place(target, '{x: 780, y: 125, width: 465, height: 460}')
                for app, binary, pos, title in [
                    ('dolphin', '/usr/bin/dolphin --new-window', (233, 200), f'{source} — Dolphin'),
                    ('explorer', '~/.local/bin/win7-explorer', (215, 230), source),
                ]:
                    source_unit = f'{unit}-{app}'
                    units.append(source_unit)
                    user(f'systemd-run --user --collect -q --unit={source_unit} --setenv=WAYLAND_DEBUG=client '
                         f'--property=StandardError=append:{root}/{backend}-{app}.trace {binary} {root}/{source}')
                    wait_for(lambda: any(r[0] == title for r in windows()), f'{app} source window')
                    actual = next(r for r in windows() if r[0] == title)
                    assert not is_x11(title) and (app != 'explorer' or actual[1] == EXPLORER), actual
                    place(title, '{x: 32, y: 96, width: 655, height: 425}')
                    time.sleep(.7)
                    shot(args.out / f'{backend}-{app}-layout.png')
                    user(f': > {root}/events')
                    drag(pos, [(pos[0] + 35, pos[1]), (545, 315), (975, 285), (1000, 302)])
                    events = [json.loads(row) for row in user(f'cat {root}/events').splitlines()]
                    (args.out / f'{backend}-{app}.json').write_text(json.dumps(events, indent=2) + '\n')
                    shot(args.out / f'{backend}-{app}-drop.png')
                    if not any(e['phase'] == 'read' and e['files'] == [dict(name=FILE, size=len(PAYLOAD), bytes=list(PAYLOAD))]
                               for e in events):
                        failures.append(f'{app} → {backend}: no matching file: {events}')
                    else:
                        print(f'{app} → {backend}: received exact filename and bytes', flush=True)
                    if app == 'explorer' and any(e['phase'] == 'read' for e in events):
                        for name, end in [('rejected', [(975, 535), (1000, 540)]),
                                          ('escaped', [(975, 285), (1000, 302)]), ('self', [])]:
                            user(f': > {root}/events; printf "\\nGESTURE {name}\\n" >> {root}/{backend}-{app}.trace')
                            drag(pos, [(pos[0] + 35, pos[1]), (545, 315), *end], cancel=name == 'escaped')
                            rejected = [json.loads(row) for row in user(f'cat {root}/events').splitlines()]
                            (args.out / f'{backend}-{name}.json').write_text(json.dumps(rejected, indent=2) + '\n')
                            assert not any(e['phase'] in ('drop', 'read') for e in rejected), (name, rejected)
                            if name == 'escaped':
                                assert any(e['phase'] == 'over' for e in rejected), rejected
                            assert user(f'ls -A {root}/{source}') == FILE
                            assert user(f'sha256sum "{root}/{source}/{FILE}"').split()[0] == PAYLOAD_HASH
                    user(f'systemctl --user stop {source_unit}', check=False)
                    trace = args.out / f'{backend}-{app}.trace'
                    vmctl.transfer(VM, 'get', str(trace), f'{root}/{backend}-{app}.trace')
                    wire = trace.read_text()
                    assert '.offer("text/uri-list")' in wire and '.set_actions(3)' in wire
                    if any(e['phase'] == 'read' for e in events):
                        assert '.send("text/uri-list"' in wire and '.action(1)' in wire
                    for name, gesture in re.findall(r'GESTURE (\w+)\n(.*?)(?=GESTURE |\Z)', wire, re.S):
                        assert '.start_drag(' in gesture, name
                        assert '.dnd_finished()' not in gesture, name
                        assert not re.search(r'wl_data_device#\d+\.drop\(', gesture), name
                        if name == 'escaped':
                            assert '.dnd_drop_performed()' not in gesture, name
                        assert re.search(r'wl_data_source#\d+\.(cancelled|destroy)\(', gesture), name
                        print(f'{backend}: {name} gesture started and did not deliver a drop', flush=True)
            finally:
                system(f'systemctl stop {unit}')
                if units:
                    user('systemctl --user stop ' + ' '.join(units), check=False)
                vmctl.transfer(VM, 'get', str(args.out / f'{backend}-target.log'), f'{root}/{backend}-target.log')
        assert not failures, '\n'.join(failures)
        # KDirOperator treats an incoming folder as navigation, not as a file move or copy.
        nonce = Path(root).name
        source, folder, target = (f'{nonce}-{role}' for role in ('incoming', 'folder', 'recipient'))
        user(f'mkdir -p {root}/{source}/{folder}; cp -r {root}/source {root}/{target}')
        inbound = [f'{nonce}-inbound-{app}' for app in ('dolphin', 'explorer')]
        try:
            for unit, command in zip(inbound, [f'dolphin --new-window {root}/{source}', f'~/.local/bin/win7-explorer {root}/{target}']):
                user(f'systemd-run --user --collect -q --unit={unit} {command}')
            def captions():
                return {r[0] for r in kwin_query('for (const w of workspace.windowList()) emit(w.caption);')}

            wait_for(lambda: {f'{source} — Dolphin', target} <= captions(), 'owned inbound windows')
            place(target, '{x: 732, y: 125, width: 470, height: 460}')
            place(f'{source} — Dolphin', '{x: 32, y: 96, width: 655, height: 425}')
            drag((216, 200), [(250, 200), (540, 310), (982, 330), (995, 345)])
            wait_for(lambda: folder in captions(), 'Explorer navigated to the external folder')
            assert user(f'ls -A {root}/{target}') == FILE
            shot(args.out / 'kio-inbound.png')
            print('Inbound Dolphin folder drag preserved native KIO navigation', flush=True)
        finally:
            user('systemctl --user stop ' + ' '.join(inbound), check=False)

        # Open two windows in one process, so Qt reports a real same-process but different view source.
        left, right = f'{Path(root).name}-from', f'{Path(root).name}-into'
        unit = f'{Path(root).name}-two-views'
        user(f'cp -r {root}/source {root}/{left}; mkdir {root}/{right}; systemd-run --user --collect -q '
             f'--unit={unit} ~/.local/bin/win7-explorer {root}/{left} {root}/{right}')
        try:
            def explorer_windows():
                return kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass === "{EXPLORER}") '
                                  'emit(w.caption, w.x, w.pid);')

            wait_for(lambda: {left, right} <= {r[0] for r in explorer_windows()}, 'both Explorer views')
            place(right, '{x: 732, y: 125, width: 470, height: 460}')
            place(left, '{x: 32, y: 96, width: 655, height: 425}')
            assert len({r[2] for r in explorer_windows() if r[0] in (left, right)}) == 1
            drag((215, 230), [(250, 230), (540, 310), (982, 330), (995, 345)])
            wait_for(lambda: any(r[:2] == [left, '732'] for r in explorer_windows()), 'right view navigated to file folder')
            image = args.out / 'kio-other-view.png'
            shot(image)
            with Image.open(image) as frame:
                frame.crop((805, 538, 908, 553)).resize((412, 60), Image.Resampling.LANCZOS).save(args.out / 'kio-selection.png')
                assert (10, 36, 106) in frame.convert('RGB').crop((910, 222, 1012, 337)).get_flattened_data(), 'target row not selected'
            selection = subprocess.check_output(['tesseract', str(args.out / 'kio-selection.png'), 'stdout', '--psm', '7'], text=True)
            assert selection.strip() == FILE, selection
            # With Open visible in this narrow target, trailing actions must not cover the View area.
            vmctl.pointer(VM, 1023, 199, 'left')
            overflow = args.out / 'command-overflow.png'
            shot(overflow)
            with Image.open(overflow) as frame:
                frame.crop((1003, 212, 1195, 295)).resize((768, 332)).save(args.out / 'command-overflow-crop.png')
            labels = subprocess.check_output(['tesseract', str(args.out / 'command-overflow-crop.png'),
                                              'stdout', '--psm', '6'], text=True)
            assert 'Share with' in labels and 'New folder' in labels, labels
            vmctl.keys(VM, 'KEY_ESC')
            vmctl.pointer(VM, 1120, 199, 'left')
            shot(args.out / 'narrow-view-menu.png')
            with Image.open(args.out / 'narrow-view-menu.png') as frame:
                frame.crop((1080, 210, 1230, 340)).resize((600, 520)).save(args.out / 'narrow-view-menu-crop.png')
            labels = subprocess.check_output(['tesseract', str(args.out / 'narrow-view-menu-crop.png'),
                                              'stdout', '--psm', '6'], text=True)
            assert 'Details' in labels, labels
            vmctl.keys(VM, 'KEY_ESC')
            assert user(f'ls -A {root}/{left}') == FILE and not user(f'ls -A {root}/{right}')
            print('Other Explorer view: KIO navigated and selected the file', flush=True)
        finally:
            user(f'systemctl --user stop {unit}', check=False)
    finally:
        user(f'rm -r {root}')


if __name__ == '__main__':
    main()
