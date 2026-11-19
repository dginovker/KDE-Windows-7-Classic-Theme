#!/usr/bin/env python3
"""Check Explorer's actual selection verbs; automatic Print checks cancel, never spool."""
import argparse
import csv
from io import BytesIO
from pathlib import Path
import subprocess
import time

from PIL import Image

from lab import VM, install, kwin_script, shot, toggle, user, vmctl, wait_for, windows
from test_explorer import EXPLORER, captions, click, exists, key
from test_explorer_command_menus import words
from test_menus import popup_bevel
from test_upgrade import output_name


def run(out, base):
    cfg = f'{base}/config'
    fixture = f'{base}/Item-verbs'
    user(f'mkdir -p {cfg} {fixture}/AFolder; cp ~/.config/kdeglobals {cfg}/; '
         f'printf "Explorer print fixture 8927\n" > {fixture}/Sample.txt; '
         f'printf "%%PDF-1.4\n" > {fixture}/Unsupported.pdf; '
         f'printf untouched > "{fixture}/Sample.txt - Shortcut"; '
         f'printf "[Default Applications]\ntext/plain=org.kde.kate.desktop;\n" > {cfg}/mimeapps.list; '
         f'XDG_CONFIG_HOME={cfg} kbuildsycoca6')
    user(f'systemd-run --user --collect -q --setenv=XDG_CONFIG_HOME={cfg} ~/.local/bin/win7-explorer {fixture}')
    wait_for(lambda: 'Item-verbs' in captions(), 'selection fixture')
    x, y = 256, 120

    def pt(a, b):
        return x + a, y + b

    def size(w):
        kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" && w.caption == "Item-verbs") '
                    f'{{ w.frameGeometry = {{x:{x},y:{y},width:{w},height:405}}; workspace.activeWindow=w; }}')

    def capture(name):
        vmctl.pointer(VM, 1170, 720)
        time.sleep(.5)
        path = out / f'{name}.png'
        shot(path)
        return Image.open(path).convert('RGB')

    def band(name):
        return words(capture(name), pt(0, 55) + pt(585, 87))

    def popup(name):
        image = capture(name)
        box = popup_bevel(image)
        assert box, f'{name}: no real popup'
        return words(image, box)

    def choose(label, name, box=None):
        image = capture(name)
        box = box or popup_bevel(image)
        assert box, f'{name}: no real popup'
        crop = image.crop(box).convert('L')
        buf = BytesIO()
        crop.resize((crop.width * 3, crop.height * 3)).save(buf, format='PNG')
        tsv = subprocess.check_output(['tesseract', 'stdin', 'stdout', '--psm', '6', 'tsv'],
                                      input=buf.getvalue(), stderr=subprocess.DEVNULL).decode()
        rows = [row for row in csv.DictReader(tsv.splitlines(), delimiter='\t') if row['text'] == label]
        assert len(rows) == 1, (label, tsv)
        row, = rows
        click((box[0] + (int(row['left']) + int(row['width']) // 2) // 3,
               box[1] + (int(row['top']) + int(row['height']) // 2) // 3))

    def cancel_print(name):
        wait_for(lambda: any('Print' in c for c in captions()), f'{name}: Qt print dialog')
        capture(name)
        key('KEY_ESC')
        wait_for(lambda: captions() == ['Item-verbs'], 'cancelled print, Explorer remains open')

    size(768)
    labels = band('unselected')
    assert 'Include in library' in labels and 'Print' not in labels, labels
    click(pt(221, 150))
    labels = band('folder')
    assert 'Include in library' in labels and 'Print' not in labels, labels
    # Files sort after folders; reach this exact file without relying on the collision file's MIME ordering.
    sample = pt(338, 150)
    click(sample)
    labels = band('text')
    assert 'Print' in labels and 'Include in library' not in labels and 'Open' in labels, labels
    choose('Print', 'toolbar-print-choice', pt(0, 55) + pt(585, 87))
    cancel_print('toolbar-print')
    click(sample, 'right')
    labels = popup('text-context')
    assert all(v in labels for v in ('Open', 'Open with', 'Edit', 'Print', 'Create shortcut')), labels
    choose('Print', 'context-print-choice')
    cancel_print('context-print')
    click(sample, 'right')
    choose('Edit', 'context-edit-choice')
    wait_for(lambda: 'Sample.txt' in windows().get('org.kde.kate', ('',))[0], 'real Kate opened selected text')
    user('pkill -u tester -x kate')
    click(sample, 'right')
    choose('Create', 'context-link-choice')
    link = f'"{fixture}/Sample.txt - Shortcut (2)"'
    wait_for(lambda: exists(link), 'second shortcut name (preexisting file protected)')
    assert user(f'realpath {link}') == f'{fixture}/Sample.txt'
    assert user(f'cat "{fixture}/Sample.txt - Shortcut"') == 'untouched'
    key('KEY_LEFTCTRL', 'KEY_Z')
    wait_for(lambda: not exists(link), 'undo removed only the new symlink')
    assert user(f'cat {fixture}/Sample.txt; cat "{fixture}/Sample.txt - Shortcut"') == 'Explorer print fixture 8927\nuntouched'
    size(300)
    # At 300px only Organize fits before the overflow; its trailing neighbor is the chevron.
    click(pt(99, 73))
    overflow = popup('text-overflow')
    assert 'Print' in overflow and 'Include in library' not in overflow, overflow
    choose('Print', 'overflow-print-choice')
    cancel_print('overflow-print')
    size(768)
    click(pt(572, 150), 'right')
    labels = popup('unsupported-context')
    assert 'Print' not in labels and 'Edit' not in labels and 'Open' in labels, labels
    key('KEY_ESC')
    click(pt(655, 275))
    labels = band('deselected')
    assert 'Include in library' in labels and 'Print' not in labels, labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true', help='use candidate already installed in the disposable lab')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.installed:
        install(reset=False)
    output = output_name()
    base = user('mktemp -d /tmp/w7-item-verbs.XXXXXX')
    toggle('current')
    user(f'kscreen-doctor output.{output}.scale.1')
    toggle('windows')
    try:
        run(args.out, base)
    finally:
        user(f'pkill -x win7-explorer || true; rm -rf {base}')
        toggle('current')
        user(f'kscreen-doctor output.{output}.scale.1')


if __name__ == '__main__':
    main()
