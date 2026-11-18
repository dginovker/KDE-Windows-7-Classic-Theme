#!/usr/bin/env python3
"""Drive the production Explorer selection pane and Open command (issue #37)."""
import argparse
import json
from pathlib import Path
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, install, kwin_query, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, click, key
from test_explorer_details import read_text, text_bands
from test_explorer_empty import unit_running

NATIVE = ROOT / 'reference/screenshots/w7-explorer-selection.png'
KATE = 'org.kde.kate'


def app_windows():
    rows = kwin_query(f'''for (const w of workspace.windowList())
        if (w.normalWindow && ["{EXPLORER}", "{KATE}"].includes(w.resourceClass))
            emit(w.pid, w.resourceClass, w.caption);''')
    return [(int(pid), app, caption) for pid, app, caption in rows]


def unit_pid(unit):
    return int(user(f'systemctl --user show {unit}.service --property=MainPID --value') or 0)


def activate(pid, place=None):
    placement = ''
    if place:
        x, y, width, height = place
        placement = f'w.frameGeometry = {{x:{x}, y:{y}, width:{width}, height:{height}}};'
    rows = kwin_query(f'''for (const w of workspace.windowList()) if (w.pid == {pid} && w.normalWindow) {{
        {placement} workspace.activeWindow = w;
        const g = w.frameGeometry;
        emit(workspace.activeWindow == w, g.x, g.y, g.width, g.height);
    }}''')
    assert len(rows) == 1 and rows[0][0] == 'true', (pid, rows)
    if place:
        def placed():
            geometry = kwin_query(f'''for (const w of workspace.windowList())
                if (w.pid == {pid} && workspace.activeWindow == w) {{
                    const g = w.frameGeometry;
                    emit(g.x, g.y, g.width, g.height);
                }}''')
            return len(geometry) == 1 and tuple(map(float, geometry[0])) == place

        wait_for(placed, f'Wayland acknowledges fixture frame {place}')


def exercise(out, scale, root, resume):
    out.mkdir(parents=True)
    folder = f'{root}/Classic-demo'
    unit = f'{Path(root).name}-{round(scale * 100)}'
    kate_unit = unit + '-kate'
    config = f'{root}/kate-{scale:g}'
    place = (256, 120, 768, 560) if scale == 1 else (40, 40, 768, 440)
    x, y, width, height = place
    explorer_pid = kate_pid = 0
    assert not app_windows() and not user('pgrep -u tester -x kate || true'), 'fixture requires a free lab Explorer/Kate session'
    # Own the Kate instance and its settings; Open still resolves the normal KDE file association.
    user(f'mkdir -p {config}/data && cp ~/.config/kdeglobals {config}/ && '
         f'printf \"Owned Kate control\\n\" > {root}/Control.txt')

    def point(dx, dy):
        return round((x + dx) * scale), round((y + dy) * scale)

    def region(x0, y0, x1, y1):
        return (*point(x0, y0), *point(x1, y1))

    def snap(tag):
        vmctl.pointer(VM, 1250, 705)
        time.sleep(.5)
        path = out / f'{tag}.png'
        shot(path)
        image = Image.open(path).convert('RGB')
        assert image.size == (1280, 800), image.size
        return image

    def check(tag, top, bottom, *, selected=True, oracle=None):
        image = snap(tag)
        rows = [region(77, height - 51 + dy, width - 10, height - 51 + dy + 16)
                for dy in (4, 22)]
        for i, (box, pieces) in enumerate(zip(rows, (top, bottom))):
            if not pieces:
                assert text_bands(image, box) == [], f'{tag}: stale metadata on row {i}'
                continue
            actual = read_text(image, out, f'{tag}-row{i}', box)
            print(f'{scale:g}x {tag} row {i}: {actual}', flush=True)
            compact = lambda s: ''.join(s.lower().split())
            assert all(compact(s) in compact(actual) for s in pieces), (tag, pieces, actual)
            if oracle is not None:
                with Image.open(NATIVE) as native:
                    target = text_bands(native, (77, oracle * 88 + 41 + i * 18, 756, oracle * 88 + 57 + i * 18))
                actual_bands = text_bands(image, box)
                assert target and actual_bands
                actual_start = (actual_bands[0][0] - box[1]) / scale
                assert abs(actual_start - (target[0][0] - (oracle * 88 + 41 + i * 18))) <= 2, (tag, actual_bands, target)
        open_box = region(108, 64, 140, 82)
        if selected:
            actual = read_text(image, out, f'{tag}-open', open_box)
            assert actual == 'Open', (tag, actual)
        else:
            return image.crop(region(4, 58, 410, 90))

    def title(pid):
        titles = [caption.split(' — ', 1)[0] for p, _, caption in app_windows() if p == pid]
        assert len(titles) <= 1, (pid, titles)
        return titles[0] if titles else None

    def close_document(name):
        activate(kate_pid)
        assert title(kate_pid) == name, f'expected active Kate document {name}'
        key('KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: title(kate_pid) != name, f'Kate closes {name}')

    def launched_folders():
        candidates = [(pid, caption) for pid, app, caption in app_windows()
                      if app == EXPLORER and pid != explorer_pid]
        for pid, caption in candidates:
            assert caption in ('Documents', 'Downloads'), (pid, caption)
            target = f'{folder}/{caption}'
            owned = user(f'''tr '\\0' '\\n' </proc/{pid}/cmdline | grep -Fx -e {target} -e file://{target}''')
            assert owned, f'cannot prove ownership of {caption} (pid {pid})'
        return candidates

    try:
        user(f'systemd-run --user --collect -q --unit={kate_unit} --setenv=XDG_CONFIG_HOME={config} '
             f'--setenv=XDG_DATA_HOME={config}/data kate --new --startanon {root}/Control.txt')
        kate_pid = unit_pid(kate_unit)
        wait_for(lambda: title(kate_pid) == 'Control.txt', 'owned Kate at the control document')
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=LC_ALL=en_US.UTF-8 '
             f'~/.local/bin/win7-explorer {folder}')
        explorer_pid = unit_pid(unit)
        wait_for(lambda: title(explorer_pid) == 'Classic-demo', 'owned Explorer selection fixture')
        activate(explorer_pid, place)
        bare = check('none', ('7 items',), (), selected=False, oracle=0)
        if not resume:
            click(point(224, 150))
            check('folder', ('Documents', 'Date modified:', '1/1/2010', '1:05 PM'), ('File folder',), oracle=1)
            click(point(122, 74))
            wait_for(lambda: title(explorer_pid) == 'Documents', 'Open navigates the existing window into Documents')
            check('opened-folder', ('0 items',), (), selected=False)
            key('KEY_LEFTALT', 'KEY_LEFT')
            wait_for(lambda: title(explorer_pid) == 'Classic-demo', 'Back to parent after Open')
            click(point(600, 365))
            assert ImageChops.difference(bare, check('back-cleared', ('7 items',), (), selected=False)).getbbox() is None

            click(point(224, 272))
            check('file', ('Alpha.txt', 'Date modified:', '1/2/2010', 'Date created:'),
                  ('Plain text document', 'Size: 17 bytes'), oracle=3)
            click(point(146, 74))
            menu = snap('open-with')
            menu_text = read_text(menu, out, 'open-with-menu', region(86, 89, 305, 160), 6)
            assert 'Kate' in menu_text or 'Open With' in menu_text, menu_text
            key('KEY_ESC')
            click(point(122, 74))
            wait_for(lambda: title(kate_pid) == 'Alpha.txt', 'KIO opens Alpha.txt in the owned Kate')
            close_document('Alpha.txt')
            assert title(kate_pid) == 'Control.txt', 'single-open document carried over into multi-open test'
            activate(explorer_pid, place)

        click(point(224, 272))
        key('KEY_LEFTSHIFT', 'KEY_RIGHT')
        if not resume:
            check('files', ('2 items selected', '1/2/2010', '1/3/2010'), ('Size: 29 bytes',), oracle=4)
        assert title(kate_pid) == 'Control.txt', 'multi-Open must start with neither selected document open'
        click(point(122, 74))

        # Titles identify the current tab, not the open set. Close each verified disposable tab
        # so the other previously opened tab must surface without any new file-open request.
        pending = {'Alpha.txt', 'Beta.txt'}
        for i in range(2):
            found = []

            def current_document():
                name = title(kate_pid)
                if name in pending:
                    found.append(name)
                return found

            wait_for(current_document, f'Kate surfaces a document from {sorted(pending)}')
            (name,) = found
            activate(kate_pid)
            snap(f'opened-document-{i}-{name}')
            close_document(name)
            pending.remove(name)
            print(f'{scale:g}x multi-Open verified in Kate: {name}', flush=True)
        assert title(kate_pid) == 'Control.txt', 'multi-Open must leave the unrelated control document intact'
        activate(explorer_pid, place)
        click(point(224, 150))
        key('KEY_LEFTSHIFT', 'KEY_RIGHT')
        check('folders', ('2 items selected', '1/1/2010', '1/4/2010'), (), oracle=2)
        click(point(122, 74))
        wait_for(lambda: {caption for _, caption in launched_folders()} == {'Documents', 'Downloads'},
                 'multi-Open opens both folders in distinct windows')
        assert title(explorer_pid) == 'Classic-demo', 'multi-Open replaced the original window'
        snap('opened-folders')
        activate(explorer_pid, place)
        click(point(600, 365))
        assert ImageChops.difference(bare, check('deselected', ('7 items',), (), selected=False)).getbbox() is None

        # A metadata change in the real listing must refresh a still-selected item.
        click(point(224, 272))
        user(f'touch -t 201001051205 {folder}/Alpha.txt')
        check('metadata-changed', ('Alpha.txt', '1/5/2010'), ('Size: 17 bytes',))
        click(point(625, 40))
        vmctl.type_text(VM, 'Beta')
        check('filtered-out-selection', ('1 item',), (), selected=False)
    except AssertionError:
        shot(out / 'failure.png')
        (out / 'failure-windows.json').write_text(json.dumps(app_windows(), indent=2) + '\n')
        raise
    finally:
        # Let the listing shut down normally rather than repeating the previous pkill teardown.
        pids = [pid for pid, _ in launched_folders()] + [explorer_pid, kate_pid]
        for pid in pids:
            if pid and any(p == pid for p, *_ in app_windows()):
                activate(pid)
                key('KEY_LEFTALT', 'KEY_F4')
                wait_for(lambda: all(p != pid for p, *_ in app_windows()), f'owned window {pid} closes')
        wait_for(lambda: not unit_running(unit) and not unit_running(kate_unit), 'owned units exit normally')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--scales', nargs='+', type=float, choices=(1, 1.5), default=(1, 1.5))
    parser.add_argument('--resume-100', action='store_true',
                        help='skip the already captured 100 percent single-item and multi-file pane checks')
    args = parser.parse_args()
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    initial = user('~/.local/bin/win7-classic status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    root = user('mktemp -d /tmp/w7-selection.XXXXXXXX')
    folder = f'{root}/Classic-demo'
    completed = False
    try:
        if initial != 'windows':
            toggle('windows')
        assert user('xdg-mime query default text/plain') == 'org.kde.kate.desktop', 'lab fixture requires Kate for text/plain'
        assert user('xdg-mime query default inode/directory') == 'org.win7classic.explorer.desktop', 'lab must be in Windows mode'
        user(f'''mkdir -p {folder}/{{Documents,Downloads,Music,Pictures,Projects}}
printf 'Classic reference' > {folder}/Alpha.txt
printf 'Another file' > {folder}/Beta.txt
touch -t 201001011305 {folder}/Documents
touch -t 201001041305 {folder}/Downloads
touch -t 201001021305 {folder}/Alpha.txt
touch -t 201001031305 {folder}/Beta.txt''')
        checksum = user(f'sha256sum {folder}/*.txt')
        for scale in args.scales:
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}; touch -t 201001021305 {folder}/Alpha.txt')
            exercise(args.out / f'scale-{scale:g}', scale, root, args.resume_100 and scale == 1)
        assert user(f'sha256sum {folder}/*.txt') == checksum
        completed = True
    finally:
        # Preserve the fixture and logs after a failed run instead of deleting files still open in a guest app.
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}')
        if completed:
            user(f'rm -r {root}')
        else:
            print(f'Guest fixture retained for diagnosis: {root}', flush=True)
        if initial != 'windows':
            toggle(initial)
    print('PASS: Explorer selection checks at ' + ', '.join(f'{scale:.0%}' for scale in args.scales))


if __name__ == '__main__':
    main()
