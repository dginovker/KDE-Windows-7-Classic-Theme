#!/usr/bin/env python3
"""Exercise actual Open/Open With dispatch and failure UI without launching the marker."""
import argparse
import csv
import json
from pathlib import Path
import shlex
import subprocess

from PIL import Image

from lab import VM, install, kwin_query, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, click, key
from test_explorer_details import read_text
from test_explorer_empty import stop_unit
from test_explorer_selection import activate, app_windows, unit_pid


def exercise(out, scale, root):
    out.mkdir(parents=True)
    config = f'{root}/config'
    folder = f'{root}/Open-fixture'
    unit = Path(root).name
    app = f'{root}/chooser-app'
    argv = f'{root}/chooser-argv'
    desktop = f'~/.local/share/applications/{unit}.desktop'
    parent, kate = 0, 0
    wide = (40, 40, 768, 440)
    narrow = (40, 40, 265, 440)
    assert not app_windows(), 'requires an unused Explorer/Kate session'
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
#!/bin/sh
printf '%s\\n' "$@" > {argv}.tmp
mv {argv}.tmp {argv}
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
        rows = kwin_query('const w = workspace.activeWindow; if (w) emit(w.pid, w.caption, w.modal);')
        return len(rows) == 1 and rows[0][0] == str(pid) and rows[0][2] == 'true' and (
            caption is None or caption in rows[0][1])

    def clear_dialog(caption):
        key('KEY_ESC')
        wait_for(lambda: not active_owned_dialog(parent, caption), f'dismissed {caption}')

    def select(x, name):
        click(point(x, 150))
        pane = (*point(69, 392), *point(360, 411))
        wait_for(lambda: name in text('selected-' + Path(name).stem, pane, 7), f'selected {name}')

    def chooser_active():
        return kwin_query('const w = workspace.activeWindow; if (w) emit(w.resourceClass, w.caption);') == [
            ['org.freedesktop.impl.portal.desktop.kde', 'Choose Application']]

    def chooser_label(tag, label):
        path = out / f'{tag}.png'
        frame = snap(tag)
        area = frame.crop((0, 100, 1080, 420))
        ocr = path.with_name(f'{tag}-ocr.png')
        area.resize((area.width * 3, area.height * 3), Image.Resampling.LANCZOS).save(ocr)
        words = subprocess.check_output(['tesseract', str(ocr), 'stdout', '--psm', '11', 'tsv'],
                                        text=True, stderr=subprocess.DEVNULL)
        matches = [row for row in csv.DictReader(words.splitlines(), delimiter='\t') if row.get('text') == label]
        if len(matches) != 1:
            return None
        left, top, width, height = (int(matches[0][field]) for field in ('left', 'top', 'width', 'height'))
        return (left + width // 2) // 3, 100 + (top + height // 2) // 3

    def choose(tag):
        wait_for(chooser_active, f'{tag} invoked the KDE application chooser')
        target = None

        def app_visible():
            nonlocal target
            target = chooser_label(tag + '-chooser', 'Recorder')
            return target

        wait_for(app_visible, 'fixture app is visible in the real chooser')
        click(target)
        wait_for(lambda: user(f'test ! -f {argv} || cat {argv}') == f'{folder}/Read.txt',
                 f'{tag} delivers only the selected path to the disposable chooser app')
        (out / f'{tag}-argv.txt').write_text(user(f'cat {argv}') + '\n')
        user(f'rm {argv}')
        print(f'{scale:g}x {tag}: chooser ran and recorded the selected path', flush=True)

    def open_with(tag, submenu=False):
        # The first KIO choice is the default handler, not the chooser.
        if not submenu:
            key('KEY_DOWN')
        key('KEY_DOWN')
        key('KEY_RIGHT')
        snap(tag + '-offered-apps')
        key('KEY_O')
        choose(tag)

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
             f'--setenv=XDG_CACHE_HOME={root}/cache ~/.local/bin/win7-explorer {folder}')
        parent = unit_pid(unit)
        wait_for(lambda: (parent, EXPLORER, 'Open-fixture') in app_windows(), 'owned Explorer')
        activate(parent, wide)
        select(459, 'Read.txt')
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
            actual = ' '.join(text(f'error-{name}').split())
            assert expected in actual, actual
            clear_dialog('Error')
            assert windows_digest() == starting, 'failed Open launched or changed an unrelated window'
            assert not user(f'test ! -e {argv} || cat {argv}'), 'failed Open ran the chooser app'
            print(f'{scale:g}x {name}: {expected}; no unrelated window or helper launch', flush=True)
    except Exception:
        shot(out / 'failure.png')
        (out / 'failure-windows.json').write_text(json.dumps(kwin_query(
            'for (const w of workspace.windowList()) emit(w.pid, w.resourceClass, w.caption, workspace.activeWindow == w, w.modal);'), indent=2) + '\n')
        raise
    finally:
        if chooser_active():
            key('KEY_ESC')
        for pid, cls, caption in sorted(app_windows(), key=lambda row: row[0] != parent):
            if pid in (parent, kate) or (cls == EXPLORER and caption == 'Documents' and user(
                    f'''tr '\\0' '\\n' </proc/{pid}/cmdline | grep -Fx -e {folder}/Documents -e file://{folder}/Documents''')):
                if active_owned_dialog(pid):
                    key('KEY_ESC')
                activate(pid)
                if pid == parent:
                    key('KEY_ESC')
                    key('KEY_ESC')
                    key('KEY_ESC')
                key('KEY_LEFTALT', 'KEY_F4')
                wait_for(lambda: all(other != pid for other, *_ in app_windows()), f'owned window {pid} closed')
        stop_unit(unit)
        stop_unit(unit + '-kate')
        after = user(manifest)
        (out / 'fixtures-after.txt').write_text(after + '\n')
        assert after == before, 'Open changed fixture data or permissions'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--scales', nargs='+', type=float, choices=(1, 1.5), default=(1, 1.5))
    args = parser.parse_args()
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    initial_mode = user('~/.local/bin/win7-classic status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    try:
        if initial_mode != 'windows':
            toggle('windows')
        for scale in args.scales:
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}')
            root = user('mktemp -d /tmp/w7-open.XXXXXXXX')
            try:
                exercise(args.out / f'scale-{scale:g}', scale, root)
            finally:
                user(f'rm -f ~/.local/share/applications/{Path(root).name}.desktop; kbuildsycoca6; '
                     f'rm -r {shlex.quote(root)}')
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}')
        if initial_mode != 'windows':
            toggle(initial_mode)
    print('PASS: real Explorer Open and Open With, overflow, mixed targets, refusal and error UI')


if __name__ == '__main__':
    main()
