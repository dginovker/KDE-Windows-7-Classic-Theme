"""Drive the installed Classic Folder View menu at 1280x800 / 100%, after manual opt-in."""
import argparse
from io import BytesIO
from pathlib import Path
import shlex
import subprocess
import time

from PIL import Image, ImageOps

from lab import VM, shot, user, vmctl, wait_for, windows
from test_explorer_command_menus import words


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('out', type=Path)
parser.add_argument('case', choices=('stock', 'stale', 'text'))
args = parser.parse_args()
args.out.mkdir(exist_ok=True, parents=True)
root = user('mktemp -d /tmp/w7-desktop-new.XXXXXXXX')
shared_dir = '/usr/local/share/templates'
output = ('W7-42-new-link', 'W7-42-empty.txt', 'W7-42-custom.txt')


def root_script(script):
    code, out, err = vmctl.run(VM, script, 30)
    assert code == 0, out + err


def key(*keys):
    vmctl.keys(VM, *('KEY_' + k for k in keys))


def cap(name):
    time.sleep(.45)
    path = args.out / (name + '.png')
    shot(path)
    return Image.open(path).convert('RGB')


def open_new(name):
    vmctl.pointer(VM, 106, 254)
    vmctl.pointer(VM, 100, 250, 'right')
    time.sleep(.3)
    key('W')
    im = cap(name)
    ocr = im.copy()
    first = (282, 359, 360, 377)
    ocr.paste(ImageOps.invert(im.crop(first)), first)
    rows = (words(ocr, first) + words(ocr, (277, 377, 535, 625))).casefold().replace("textfile", "text file")
    print(name, repr(rows))
    assert 'folder' in rows and 'link to location' in rows and 'link to application' in rows, rows
    return im, rows


def click_row(image, label, index=0, count=1):
    crop = image.crop((277, 377, 535, 625)).convert('L')
    crop = crop.resize((crop.width * 3, crop.height * 3))
    png = BytesIO()
    crop.save(png, format='PNG')
    boxes = subprocess.check_output(['tesseract', 'stdin', 'stdout', '--psm', '6', 'tsv'],
                                    input=png.getvalue(), stderr=subprocess.DEVNULL).decode()
    rows = {}
    for line in boxes.splitlines()[1:]:
        row = line.split('\t')
        if row[0] == '5':
            rows.setdefault(tuple(row[2:5]), []).append(row)
    found = [r for r in rows.values() if label in ' '.join(t[11].casefold() for t in r).replace('textfile', 'text file')]
    assert len(found) == count, (label, rows)
    row = found[index][0]
    y = (int(row[7]) + int(row[9]) / 2) / 3 + 377
    vmctl.pointer(VM, 346, round(y), 'left')


def prompt(title):
    wait_for(lambda: any(title in w[0] for w in windows().values()), title, 6)


def create_copy(name):
    prompt('Create New')
    cap('copy-prompt')
    key('LEFTCTRL', 'A')
    vmctl.type_text(VM, name)
    key('ENTER')
    wait_for(lambda: user(f'test -f ~/Desktop/{name} && test ! -L ~/Desktop/{name} && '
                          f'cmp ~/Desktop/{name} {root}/target && echo exact', check=False) == 'exact', 'exact regular copy')
    print(user(f'stat -c "%F %s %n" ~/Desktop/{name}; sha256sum ~/Desktop/{name} {root}/target'))


def shortcut(undo):
    key('DOWN')
    key('ENTER')
    if args.case == 'stale' and any('Create New' in w[0] for w in windows().values()):
        create_copy(output[0])
        raise AssertionError('Shortcut dispatched the cached shared regular-file copy')
    prompt('Create Symlink')
    cap('shortcut-dialog')
    key('LEFTCTRL', 'A')
    vmctl.type_text(VM, output[0])
    key('TAB')
    vmctl.type_text(VM, root + '/target')
    key('ENTER')
    link = f'~/Desktop/{output[0]}'
    wait_for(lambda: user(f'readlink {link}', check=False) == root + '/target', 'exact local symlink')
    print(user(f'stat -c "%F %n" {link}; readlink {link}; cmp {link} {root}/target'))
    if undo:
        vmctl.pointer(VM, 100, 250, 'right')
        im = cap('undo-menu')
        assert 'undo' in words(im, (103, 250, 310, 535)).casefold()
        vmctl.pointer(VM, 147, 455, 'left')
        wait_for(lambda: user(f'test ! -L {link} && test -f {root}/target && echo exact') == 'exact', 'KIO Undo removes only the link')
        print('Undo removed the symlink and kept its target')


home_templates = False
shared = None
made_shared_dir = False
clean_output = False
try:
    assert user('kreadconfig6 --file plasma-org.kde.plasma.desktop-appletsrc --group ActionPlugins --group 0 --key "RightButton;NoModifier"') == 'org.win7classic.desktopmenu'
    user(f'printf "Distinct nonempty template bytes\\n" > {root}/target; '
         'for f in ' + ' '.join(f'~/Desktop/{name}' for name in output) + '; do test ! -e "$f" && test ! -L "$f" || exit 1; done')
    clean_output = True
    if args.case == 'stale':
        user('test -d ~/Templates && test -z "$(find ~/Templates -mindepth 1 -print -quit)"')
        home_templates = True
        user(f'printf "Original home source\\n" > {root}/home-target; '
             f'printf "[Desktop Entry]\\nType=Link\\nName=Home Copy Template\\nURL={root}/home-target\\n" > ~/Templates/linkPath.desktop; '
             'for n in 1 2 3 4 5 6; do printf "[Desktop Entry]\\nType=Link\\nName=Ignored\\nNoDisplay=true\\n" > ~/Templates/W7-42-Ignored$n.desktop; done')
    if args.case in ('stale', 'text'):
        filename, label, icon = (('linkURL.desktop', 'Link to File or Directory...', 'emblem-symbolic-link')
                                 if args.case == 'stale' else ('CustomText.desktop', 'Text File...', 'text-plain'))
        _, stdout, _ = vmctl.run(VM, f'test -d {shared_dir} && echo present', 10)
        made_shared_dir = stdout.strip() != 'present'
        path = f'{shared_dir}/{filename}'
        spec = f'[Desktop Entry]\nType=Link\nName={label}\nIcon={icon}\nURL={root}/target\n'
        root_script(f'set -eu; mkdir -p {shared_dir}; set -C; printf %s {shlex.quote(spec)} > {path}')
        shared = path
    # Load exactly one initial KIO cache; do not refresh Plasma between stale-case openings.
    user('systemctl --user reset-failed plasma-plasmashell; systemctl --user restart plasma-plasmashell')
    time.sleep(3)
    pid = user('pidof plasmashell')
    plugin = '/usr/lib/qt6/plugins/plasma/containmentactions/org.win7classic.desktopmenu.so'
    _, rows = open_new('initial-cache')
    print(user(f'grep -m1 "{plugin}" /proc/{pid}/maps; sha256sum "{plugin}"'))
    if args.case == 'stale':
        assert 'home copy template' in rows and 'link to file or directory' in rows, rows
        key('ESC'); key('ESC')
        user(f'rm {root}/home-target; test -f ~/Templates/linkPath.desktop')
        im, rows = open_new('after-removing-only-external-target')
        assert user('pidof plasmashell') == pid
        assert 'home copy template' in rows, 'KIO did not retain the cached home row'
        assert 'shortcut' in rows and 'shortcut unavailable' not in rows, rows
        shortcut(undo=True)
        im, rows = open_new('original-kde-shared-copy')
        assert rows.count('link to file or directory') == 1, rows
        click_row(im, 'link to file or directory')
        create_copy(output[2])
    elif args.case == 'text':
        assert rows.count('text file') == 2 and 'text document' in rows, rows
        assert rows.index('text document') < rows.index('text file'), rows
        key('T')
        prompt('Create Text Document')
        cap('empty-text-prompt')
        key('LEFTCTRL', 'A')
        vmctl.type_text(VM, output[1]); key('ENTER')
        target = f'~/Desktop/{output[1]}'
        wait_for(lambda: user(f'test -f {target} && test ! -L {target} && test ! -s {target} && echo exact', check=False) == 'exact', 'empty regular Text Document')
        print(user(f'stat -c "%F %s %n" {target}'))
        im, _ = open_new('original-kde-text-templates')
        # The stock resource and same-named custom template are both retained. Their stock
        # order is built-in TextFile then ordinary templates; use the last identical row.
        click_row(im, 'text file', index=1, count=2)
        create_copy(output[2])
    else:
        assert rows.index('folder') < rows.index('shortcut') < rows.index('text document'), rows
        assert 'link to file or directory' in rows and 'text file' in rows, rows
        shortcut(undo=True)
    print('PASS', args.case)
finally:
    if shared:
        root_script(f'rm {shared}' + (f'; rmdir {shared_dir}' if made_shared_dir else ''))
    if home_templates:
        user('rm ~/Templates/{linkPath,W7-42-Ignored{1,2,3,4,5,6}}.desktop')
    user(f'rm -r {root}')
    if clean_output:
        user('rm -f ' + ' '.join(f'~/Desktop/{name}' for name in output))
