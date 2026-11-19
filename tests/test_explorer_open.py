#!/usr/bin/env python3
"""Exercise actual Open/Open With dispatch and failure UI without launching the marker."""
import argparse
import csv
import json
from pathlib import Path
import shlex
import subprocess

from PIL import Image

from lab import VM, clipboard, executable, explorer_identity, install, kwin_query, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, click, key
from test_explorer_details import read_text
from test_explorer_empty import stop_unit
from test_explorer_selection import activate, app_windows, unit_pid


def exercise(out, scale, root, explorer):
    out.mkdir(parents=True)
    config = f'{root}/config'
    folder = f'{root}/Open-fixture'
    unit = Path(root).name
    app = f'{root}/chooser-app'
    argv = f'{root}/chooser-argv'
    desktop = f'~/.local/share/applications/{unit}.desktop'
    parent, kate = 0, 0
    owned_chooser = None
    wide = (40, 40, 768, 440)
    narrow = (40, 40, 265, 440)
    assert not app_windows() and not user('pgrep -x kwrite || true'), 'requires an unused Explorer/editor session'
    user(f'''mkdir -p {config} {root}/cache {root}/kate {folder}/Documents
cp ~/.config/kdeglobals {config}/
cp ~/.config/kdeglobals {root}/kate/
cat > {config}/mimeapps.list <<'EOF'
[Default Applications]
text/plain=org.kde.kate.desktop;
inode/directory=org.win7classic.explorer.desktop;
EOF
printf 'owned control\\n' > {root}/Control.txt
printf 'owned document\\n' > {folder}/Read.txt
printf 'owned folder contents\\n' > {folder}/Documents/Keep.txt
printf '[Desktop Entry]\\nName=Broken entry\\n' > {folder}/Broken.desktop
cat > {app} <<'EOF'
#!/usr/bin/python
import json
from pathlib import Path
import sys

record = Path('{argv}')
tmp = record.with_suffix('.tmp')
tmp.write_text(json.dumps(sys.argv[1:]) + '\\n')
tmp.replace(record)
EOF
chmod u+x {app}
test ! -e {desktop} && cat > {desktop} <<'EOF'
[Desktop Entry]
Type=Application
Name=Fixture Recorder
Icon=accessories-text-editor
Exec={app} %f
MimeType=text/plain;
EOF
kbuildsycoca6
# A recognizable ELF executable MIME type, but no architecture, entry point, or segments to run.
python - {folder}/RefusalMarker <<'EOF'
from pathlib import Path
import sys
marker = Path(sys.argv[1])
marker.write_bytes(Path('/usr/bin/true').read_bytes()[:18] + bytes(46) + b'owned inert Open refusal fixture')
marker.chmod(0o700)
EOF
file --mime-type {folder}/RefusalMarker''')
    manifest = f'cd {folder} && find . -type f -print0 | sort -z | xargs -0 sha256sum; find {folder} -printf "%m %p\\n" | sort'
    before = user(manifest)
    (out / 'fixtures-before.txt').write_text(before + '\n')

    def snap(tag):
        path = out / f'{tag}.png'
        shot(path)
        with Image.open(path) as image:
            assert image.size == (1280, 800), image.size
            return image.convert('RGB')

    def point(x, y):
        return round((wide[0] + x) * scale), round((wide[1] + y) * scale)

    def text(tag, box=None, psm=11):
        return read_text(snap(tag), out, tag + '-ocr', box or (0, 0, 1280, 760), psm)

    def active_owned_dialog(pid, caption=None):
        rows = kwin_query('''const w = workspace.activeWindow;
            if (w && w.modal) {
                const g = w.frameGeometry;
                emit(w.pid, w.caption, g.x, g.y, g.width, g.height);
            }''')
        if len(rows) == 1 and rows[0][0] == str(pid) and (caption is None or caption in rows[0][1]):
            return tuple(map(float, rows[0][2:]))
        return None

    def clear_dialog(caption):
        key('KEY_ESC')
        wait_for(lambda: not active_owned_dialog(parent, caption), f'dismissed {caption}')

    def select(x, name):
        click(point(x, 150))
        pane = (*point(69, 392), *point(360, 411))
        wait_for(lambda: name in text('selected-' + Path(name).stem, pane, 7), f'selected {name}')

    def chooser_windows():
        rows = kwin_query('''for (const w of workspace.windowList())
            if (w.resourceClass == "org.freedesktop.impl.portal.desktop.kde" && w.caption == "Choose Application")
                emit(w.internalId, workspace.activeWindow == w);''')
        windows = {wid: active == 'true' for wid, active in rows}
        assert len(windows) == len(rows) and all(windows), rows
        return windows

    def chooser_closed(wid):
        # Do not count a caption or focus change as closing the window.
        return [wid] not in kwin_query('for (const w of workspace.windowList()) emit(w.internalId);')

    def recorder_exists():
        return user(f'if test -e {argv}; then echo present; fi') == 'present'

    def label_point(tag, label, box, psm=11):
        path = out / f'{tag}.png'
        frame = snap(tag)
        area = frame.crop(box)
        ocr = path.with_name(f'{tag}-ocr.png')
        area.resize((area.width * 3, area.height * 3), Image.Resampling.LANCZOS).save(ocr)
        words = subprocess.check_output(['tesseract', str(ocr), 'stdout', '--psm', str(psm), 'tsv'],
                                        text=True, stderr=subprocess.DEVNULL)
        matches = [row for row in csv.DictReader(words.splitlines(), delimiter='\t') if row.get('text') == label]
        if len(matches) != 1:
            return None
        left, top, width, height = (int(matches[0][field]) for field in ('left', 'top', 'width', 'height'))
        return box[0] + (left + width // 2) // 3, box[1] + (top + height // 2) // 3

    def choose(tag, existing):
        nonlocal owned_chooser
        target = None

        def new_chooser_active():
            nonlocal owned_chooser
            windows = chooser_windows()
            new = windows.keys() - existing.keys()
            assert len(new) <= 1, (tag, existing, windows)
            if new:
                (wid,) = new
                if windows[wid]:
                    owned_chooser = wid
                    return True
            return False

        wait_for(new_chooser_active, f'{tag} opened a new foreground KDE application chooser')
        opened = owned_chooser
        print(f'{scale:g}x {tag}: existing choosers {existing}; foreground chooser {opened}', flush=True)

        def app_visible():
            nonlocal target
            target = label_point(tag + '-chooser', 'Recorder', (0, 100, 1080, 420))
            return target

        wait_for(app_visible, 'fixture app is visible in the real chooser')
        assert chooser_windows().get(opened), f'{tag}: {opened} lost foreground before app selection'
        click(target)
        wait_for(lambda: chooser_closed(opened), f'{tag} closed chooser {opened}')
        owned_chooser = None
        wait_for(recorder_exists, f'{tag} launched the disposable recorder')
        recorded = user(f'cat {argv}')
        (out / f'{tag}-argv.json').write_text(recorded + '\n')
        assert json.loads(recorded) == [f'{folder}/Read.txt'], (tag, recorded)
        user(f'rm {argv}')
        print(f'{scale:g}x {tag}: closed {opened}; recorder argv {recorded}', flush=True)

    def open_with(tag, submenu=False):
        # The first KIO choice is the default handler, not the chooser.
        if not submenu:
            key('KEY_DOWN')
        key('KEY_DOWN')
        key('KEY_RIGHT')
        snap(tag + '-offered-apps')
        assert not recorder_exists(), f'{tag}: stale recorder file'
        existing = chooser_windows()
        key('KEY_O')
        choose(tag, existing)

    def item_popup(label, tag):
        origin = point(459, 150)
        click(origin, 'right')
        x, y = origin
        x += round(21 * scale)  # Exclude icons from label OCR.
        crop = snap(tag).crop((x, y, x + round(120 * scale), y + round(139 * scale)))
        ocr = out / f'{tag}-ocr.png'
        crop.resize((crop.width * 3, crop.height * 3)).save(ocr)
        tsv = subprocess.check_output(['tesseract', str(ocr), 'stdout', '--psm', '6', 'tsv'],
                                      text=True, stderr=subprocess.DEVNULL)
        (out / f'{tag}.tsv').write_text(tsv)
        lines = {}
        for row in csv.DictReader(tsv.splitlines(), delimiter='\t'):
            if row['text']:
                ident = tuple(row[k] for k in ('block_num', 'par_num', 'line_num'))
                lines.setdefault(ident, []).append(row)
        matches = [line for line in lines.values() if ' '.join(
            ''.join(c for c in word['text'] if c.isalpha()) for word in line).strip().casefold() == label]
        assert len(matches) == 1, (label, tsv)
        word = next(w for w in matches[0] if w['text'].isalpha())
        return x + (int(word['left']) + int(word['width']) // 2) // 3, y + (int(word['top']) + int(word['height']) // 2) // 3

    def verify_editor(tag):
        snap(tag)
        key('KEY_LEFTCTRL', 'KEY_A')
        key('KEY_LEFTCTRL', 'KEY_C')
        copied = clipboard()
        assert copied == 'owned document', (tag, copied)
        (out / f'{tag}-copied.txt').write_text(copied + '\n')

    def overflow():
        click(point(102, 74))
        observed = text('overflow-menu', (*point(75, 87), *point(275, 185)))
        assert 'Open' in observed, observed

    def windows_digest():
        return sorted(kwin_query('for (const w of workspace.windowList()) if (w.normalWindow) emit(w.pid, w.resourceClass, w.caption);'))

    try:
        user(f'systemd-run --user --collect -q --unit={unit}-kate --setenv=XDG_CONFIG_HOME={root}/kate '
             f'kate --new --startanon {root}/Control.txt')
        kate = unit_pid(unit + '-kate')
        wait_for(lambda: any(pid == kate and c.startswith('Control.txt') for pid, _, c in app_windows()), 'owned Kate control')
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=LC_ALL=en_US.UTF-8 --setenv=XDG_CONFIG_HOME={config} '
             f'--setenv=XDG_CACHE_HOME={root}/cache {explorer} {folder}')
        parent = unit_pid(unit)
        wait_for(lambda: (parent, EXPLORER, 'Open-fixture') in app_windows(), 'owned Explorer')
        explorer_identity(parent, explorer, out)
        activate(parent, wide)
        wait_for(lambda: 'Read.txt' in text('fixture-loaded', (*point(400, 185), *point(512, 220)), 7),
                 'KIO listed the text item before pointer input')
        select(459, 'Read.txt')
        click(item_popup('open', 'context-open-menu'))
        wait_for(lambda: any(pid == kate and c.startswith('Read.txt') for pid, _, c in app_windows()),
                 'item popup Open delivered the selected file to Kate')
        activate(kate)
        verify_editor('context-open-kate')
        key('KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: any(pid == kate and c.startswith('Control.txt') for pid, _, c in app_windows()),
                 'Kate closed the selected document')
        activate(parent, wide)
        select(459, 'Read.txt')
        click(item_popup('open with', 'context-open-with-menu'))
        target = None

        def kwrite_offered():
            nonlocal target
            target = label_point('context-open-with-submenu', 'KWrite', (*point(646, 224), *point(745, 278)), 6)
            return target

        wait_for(kwrite_offered, 'text-item Open With submenu offers KWrite')
        click(target)
        wait_for(lambda: user('pgrep -x kwrite || true'), 'item popup Open With launched KWrite')
        (kwrite,) = map(int, user('pgrep -x kwrite').splitlines())
        wait_for(lambda: kwin_query(f'''const w = workspace.activeWindow;
            if (w && w.pid == {kwrite} && w.caption.startsWith('Read.txt')) emit(w.pid);'''),
                 'KWrite shows the selected document')
        verify_editor('context-open-with-kwrite')
        selected = user(f'''tr '\\0' '\\n' </proc/{kwrite}/cmdline | grep -Fx -e {folder}/Read.txt -e file://{folder}/Read.txt''')
        (out / 'context-open-with-kwrite-path.txt').write_text(selected + '\n')
        print(f'{scale:g}x item popup Open: Kate displayed selected document; Open With: KWrite received {selected}', flush=True)
        key('KEY_LEFTALT', 'KEY_F4')
        wait_for(lambda: not user('pgrep -x kwrite || true'), 'KWrite closed')
        activate(parent, wide)
        click(point(146, 74))
        snap('toolbar-open-with-menu')
        open_with('toolbar-open-with')

        activate(parent, narrow)
        overflow()
        key('KEY_DOWN')
        key('KEY_DOWN')
        key('KEY_RIGHT')
        snap('overflow-open-with-menu')
        open_with('overflow-open-with', submenu=True)
        activate(parent, narrow)
        overflow()
        key('KEY_DOWN')
        key('KEY_ENTER')
        wait_for(lambda: any(pid == kate and c.startswith('Read.txt') for pid, _, c in app_windows()), 'hidden Open opens the real text file')
        snap('overflow-open-result')
        activate(kate)
        key('KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: any(pid == kate and c.startswith('Control.txt') for pid, _, c in app_windows()), 'Kate returns to unrelated control tab')

        activate(parent, wide)
        select(218, 'Documents')
        vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_RIGHT')
        vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_RIGHT')
        key('KEY_LEFTCTRL', 'KEY_SPACE')
        pane = (*point(69, 392), *point(360, 411))
        assert '2 items selected' in text('mixed-before', pane, 7)
        click(point(122, 74))
        wait_for(lambda: any(pid == kate and c.startswith('Read.txt') for pid, _, c in app_windows()), 'mixed Open delivers text to Kate')
        wait_for(lambda: any(pid != parent and c == 'Documents' for pid, _, c in app_windows()), 'mixed Open creates a separate folder window')
        child, = (pid for pid, cls, c in app_windows() if cls == EXPLORER and c == 'Documents')
        assert user(f'''tr '\\0' '\\n' </proc/{child}/cmdline | grep -Fx -e {folder}/Documents -e file://{folder}/Documents''')
        snap('mixed-results')
        activate(parent, wide)
        assert (parent, EXPLORER, 'Open-fixture') in app_windows()
        assert '2 items selected' in text('mixed-retained', pane, 7)

        for cell, name, expected in ((575, 'RefusalMarker', 'launching executables is not allowed'),
                                     (338, 'Broken.desktop', 'has no Type')):
            select(cell, name)
            starting = windows_digest()
            click(point(122, 74))
            wait_for(lambda: active_owned_dialog(parent, 'Error'), f'visible Open error for {name}')
            frame = active_owned_dialog(parent, 'Error')
            assert frame, f'{name}: Error lost foreground before capture'
            x, y, w, h = frame
            # OCR only the owned dialog's message, not the files and windows behind it.
            box = tuple(round(n * scale) for n in (x + 60, y + 26, x + w - 6, y + h - 42))
            actual = ' '.join(text(f'error-{name}', box, 6).split())
            assert expected in actual, actual
            clear_dialog('Error')
            assert windows_digest() == starting, 'failed Open launched or changed an unrelated window'
            assert not recorder_exists(), f'{name}: failed Open ran the chooser app'
            print(f'{scale:g}x {name}: {expected}; no unrelated window or helper launch', flush=True)
    except Exception:
        shot(out / 'failure.png')
        (out / 'failure-windows.json').write_text(json.dumps(kwin_query(
            'for (const w of workspace.windowList()) emit(w.internalId, w.pid, w.resourceClass, w.caption, w.active, w.modal);'), indent=2) + '\n')
        raise
    finally:
        if owned_chooser is not None and chooser_windows().get(owned_chooser):
            key('KEY_ESC')
            wait_for(lambda: chooser_closed(owned_chooser), f'closed owned chooser {owned_chooser}')
        for pid, cls, caption in sorted(app_windows(), key=lambda row: row[0] != parent):
            if pid in (parent, kate) or (cls == EXPLORER and caption == 'Documents' and user(
                    f'''tr '\\0' '\\n' </proc/{pid}/cmdline | grep -Fx -e {folder}/Documents -e file://{folder}/Documents''')):
                if active_owned_dialog(pid):
                    key('KEY_ESC')
                    if not any(other == pid for other, *_ in app_windows()):
                        continue
                activate(pid)
                if pid == parent:
                    key('KEY_ESC')
                    key('KEY_ESC')
                    key('KEY_ESC')
                key('KEY_LEFTALT', 'KEY_F4')
                wait_for(lambda: all(other != pid for other, *_ in app_windows()), f'owned window {pid} closed')
        stop_unit(unit)
        stop_unit(unit + '-kate')
        user('pkill -x kwrite || true')
        after = user(manifest)
        (out / 'fixtures-after.txt').write_text(after + '\n')
        assert after == before, 'Open changed fixture data or permissions'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    installed = parser.add_mutually_exclusive_group()
    installed.add_argument('--installed', action='store_true', help='use the existing development install')
    installed.add_argument('--packaged', action='store_true', help='use the installed system package instead of the development install')
    parser.add_argument('--scales', nargs='+', type=float, choices=(1, 1.5), default=(1, 1.5))
    args = parser.parse_args()
    vmctl.start(VM)
    if not (args.installed or args.packaged):
        install(reset=False)
    explorer = executable('win7-explorer', args.packaged)
    tool = executable('win7-classic', args.packaged)
    initial_mode = user(f'{tool} status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    try:
        if initial_mode != 'windows':
            toggle('windows', packaged=args.packaged)
        for scale in args.scales:
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}')
            root = user('mktemp -d /tmp/w7-open.XXXXXXXX')
            try:
                exercise(args.out / f'scale-{scale:g}', scale, root, explorer)
            finally:
                user(f'rm -f ~/.local/share/applications/{Path(root).name}.desktop; kbuildsycoca6; '
                     f'rm -r {shlex.quote(root)}')
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}')
        if initial_mode != 'windows':
            toggle(initial_mode, packaged=args.packaged)
    print('PASS: real Explorer Open and Open With, overflow, mixed targets, refusal and error UI')


if __name__ == '__main__':
    main()
