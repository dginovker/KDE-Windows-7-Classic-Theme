#!/usr/bin/env python3
"""Check Explorer's actual selection verbs; printing exclusively to a controlled PDF."""
import argparse
import csv
from io import BytesIO
from pathlib import Path
import subprocess
import time
import unicodedata

from PIL import Image

from lab import VM, clipboard, executable, explorer_identity, install, kwin_query, kwin_script, shot, toggle, user, vmctl, wait_for, windows
from test_explorer import EXPLORER, captions, click, exists, key
from test_explorer_command_menus import words
from test_explorer_selection import app_windows, unit_pid
from test_menus import popup_bevel
from test_upgrade import output_name


def run(out, base, scale, explorer):
    assert not app_windows(), 'requires an unused Explorer/Kate session'
    cfg = f'{base}/config'
    fixture = f'{base}/Item-verbs'
    user(f'mkdir -p {cfg} {fixture}/AFolder {base}/Documents;  cp ~/.config/kdeglobals {cfg}/; '
         f'printf "Explorer print fixture 8927\n" > {fixture}/Sample.txt; '
         f'printf "%%PDF-1.4\n" > {fixture}/Unsupported.pdf; '
         f'printf untouched > "{fixture}/Sample.txt - Shortcut"; '
         f'printf \"XDG_DOCUMENTS_DIR=\\\"{base}/Documents\\\"\\n\" > {cfg}/user-dirs.dirs; '
         f'printf "[Default Applications]\ntext/plain=org.kde.kate.desktop;\n" > {cfg}/mimeapps.list; '
         f'XDG_CONFIG_HOME={cfg} kbuildsycoca6')
    unit = Path(base).name
    user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={cfg} {explorer} {fixture}')
    pid = unit_pid(unit)
    wait_for(lambda: (pid, EXPLORER, 'Item-verbs') in app_windows(), 'selection fixture')
    explorer_identity(pid, explorer, out)
    x, y = (256, 120) if scale == 1 else (27, 38)

    def pt(a, b):
        return round((x + a) * scale), round((y + b) * scale)

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
        labels = words(capture(name), pt(0, 55) + pt(585, 87)).replace('Includeinlibrary', 'Include in library')
        print(name, labels.strip(), flush=True)
        return labels

    def menu_box(image, name):
        if scale == 1:
            return popup_bevel(image)
        if 'overflow' in name:
            return pt(72, 86) + pt(282, 223)
        a = 572 if 'unsupported' in name else 338
        return pt(a, 150) + pt(a + 183, 350)

    def popup(name):
        image = capture(name)
        box = menu_box(image, name)
        assert box, f'{name}: no real popup'
        labels = words(image, box)
        print(name, labels.strip(), flush=True)
        return labels

    def choose(label, name, box=None):
        image = capture(name)
        box = box or menu_box(image, name)
        assert box, f'{name}: no real popup'
        crop = image.crop(box).convert('L')
        buf = BytesIO()
        crop.resize((crop.width * 3, crop.height * 3)).save(buf, format='PNG')
        tsv = subprocess.check_output(['tesseract', 'stdin', 'stdout', '--psm', '6', 'tsv'],
                                      input=buf.getvalue(), stderr=subprocess.DEVNULL).decode()
        rows = [row for row in csv.DictReader(tsv.splitlines(), delimiter='\t') if (row['text'] or '').strip() == label]
        assert len(rows) == 1, (label, tsv)
        row, = rows
        click((box[0] + (int(row['left']) + int(row['width']) // 2) // 3,
               box[1] + (int(row['top']) + int(row['height']) // 2) // 3))

    def print_pdf(name):
        def modal():
            return kwin_query(f'''const w = workspace.activeWindow;
                if (w && w.resourceClass == "{EXPLORER}" && w.caption == "Print" && w.modal) {{
                    const g = w.frameGeometry; emit(g.x, g.y, g.width, g.height);
                }}''')
        wait_for(modal, f'{name}: Qt print dialog')
        (frame,) = modal()
        ax, ay, width, height = map(float, frame)
        def dialog_box():
            return tuple(round(n * scale) for n in (ax, ay, ax + width, ay + height))
        def dialog_point(dx, dy):
            return round((ax + dx) * scale), round((ay + dy) * scale)
        def fields(tag):
            return words(capture(name + '-' + tag), dialog_box())
        # Submit only to Qt's local PDF destination. Abort rather than risk spooling to a queue.
        observed = fields('dialog')
        assert 'Local file' in observed and 'Write PDF file' in observed, (frame, observed)
        dest = f'{base}/{name}.pdf'
        assert not exists(dest), dest
        click(dialog_point(160, height - 66))
        key('KEY_LEFTCTRL', 'KEY_A')
        vmctl.type_text(VM, dest)
        observed = fields('pdf-destination')
        assert 'Write PDF file' in observed, observed
        key('KEY_LEFTCTRL', 'KEY_A')
        key('KEY_LEFTCTRL', 'KEY_C')
        assert clipboard() == dest, f'{name}: PDF destination field does not match {dest}'
        click(dialog_point(width - 137, height - 27))
        wait_for(lambda: exists(dest) and not modal(), f'{name}: PDF written and dialog closed')
        assert captions() == ['Item-verbs'], captions()
        text = user(f'pdftotext {dest} -')
        assert 'Explorer print fixture 8927' in unicodedata.normalize("NFKC", text).splitlines(), text
        vmctl.transfer(VM, 'get', str(out / f'{name}.pdf'), dest)
        (out / f'{name}.txt').write_text(text + '\n')
        print(f'{name}: real Qt PDF, {user(f"sha256sum {dest}")}', flush=True)
        user(f'rm {dest}')

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
    print_pdf('toolbar-print')
    click(sample, 'right')
    labels = popup('text-context')
    assert all(v in labels for v in ('Open', 'Open with', 'Edit', 'Print', 'Create shortcut')), labels
    choose('Print', 'context-print-choice')
    print_pdf('context-print')
    click(sample, 'right')
    choose('Edit', 'context-edit-choice')
    wait_for(lambda: 'Sample.txt' in windows().get('org.kde.kate', ('',))[0], 'real Kate opened selected text')
    capture('kate-edit')
    kate = windows()['org.kde.kate']
    assert kate[1] and 'Sample.txt' in kate[0], kate
    key('KEY_LEFTALT', 'KEY_F4')
    wait_for(lambda: 'org.kde.kate' not in windows(), 'closed edited document')
    click(sample, 'right')
    choose('Create', 'context-link-choice')
    link = f'"{fixture}/Sample.txt - Shortcut (2)"'
    wait_for(lambda: exists(link), 'second shortcut name (preexisting file protected)')
    user(f'test -L {link}')
    assert user(f'readlink -f {link}') == f'{fixture}/Sample.txt'
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
    print_pdf('overflow-print')
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
    installed = parser.add_mutually_exclusive_group()
    installed.add_argument('--installed', action='store_true', help='use the existing development install')
    installed.add_argument('--packaged', action='store_true', help='use the installed system package instead of the development install')
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not (args.installed or args.packaged):
        install(reset=False)
    output = output_name()
    base = user('mktemp -d /tmp/w7-verb.XXXXXX')
    toggle('current', packaged=args.packaged)
    user(f'kscreen-doctor output.{output}.scale.{args.scale}')
    toggle('windows', packaged=args.packaged)
    try:
        run(args.out, base, args.scale, executable('win7-explorer', args.packaged))
    finally:
        user(f'systemctl --user stop {Path(base).name}.service 2>/dev/null || true; rm -rf {base}')
        toggle('current', packaged=args.packaged)
        user(f'kscreen-doctor output.{output}.scale.1')


if __name__ == '__main__':
    main()
