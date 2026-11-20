#!/usr/bin/env python3
"""Drive the Libraries landing page, XDG overrides, ordinary Home and history."""
import argparse
from pathlib import Path

from lab import VM, clipboard, executable, explorer_identity, install, toggle, user, wait_for
from test_explorer import captions, click, double_click, key
from test_explorer_command_menus import words
from test_explorer_computer import address, area, arrange, capture
from test_explorer_selection import unit_pid
from test_upgrade import output_name


FOLDERS = ('Custom-Docs', 'Lab-Music', 'Lab-Pictures', 'Lab-Videos')
LABELS = ('Documents', 'Music', 'Pictures', 'Videos')


def check_landing(image, pt):
    # The genuine artwork next to each label confuses OCR; read only the text cells.
    labels = [words(image, pt(176, 97) + pt(430, 117)).strip(),
              words(image, pt(176, 116) + pt(502, 133)).strip()]
    assert labels == ['Libraries', 'Open a library to see your files in its configured folder.'], labels
    for i, title in enumerate(LABELS):
        x, y = 234 + 254 * (i % 2), 146 + 56 * (i // 2)
        observed = words(image, pt(x, y) + pt(x + 100, y + 29)).split()
        assert observed == [title, 'Library'], observed
    count = words(image, pt(80, 354) + pt(170, 381)).strip()
    assert count == '4 items', count
    print(f'landing: {labels}; {LABELS} each marked Library; {count}', flush=True)


def run(out, scale, base, exe, unavailable):
    assert not captions(), 'requires no open Explorer windows'
    cfg = f'{base}/config'
    sources = f'{base}/Sources'
    xdg = '\n'.join(f'XDG_{kind.upper()}_DIR="{base}/{folder}"' for kind, folder in zip(LABELS, FOLDERS))
    user(f'mkdir -p {cfg} {sources}/IncludeMe {base}/IncludeCurrent '
         + ' '.join(f'{base}/{folder}' for folder in FOLDERS)
         + f"; cp ~/.config/kdeglobals {cfg}/; printf '%s\n' '{xdg}' > {cfg}/user-dirs.dirs")
    user('; '.join(f'printf "%s\n" "{name} fixture" > {base}/{name}/Proof.txt'
                   for name in (*FOLDERS, 'Sources/IncludeMe', 'IncludeCurrent')))
    unit = Path(base).name

    def tree():
        return user(f'cd {base}; find {" ".join(FOLDERS)} Sources IncludeCurrent -printf "%y %p %l\n" | sort; '
                    f'find {" ".join(FOLDERS)} Sources IncludeCurrent -type f -exec sha256sum {{}} + | sort; '
                    'sha256sum config/user-dirs.dirs')

    before = tree()
    user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={cfg} {exe} /home/tester')
    wait_for(lambda: captions() == ['tester'], 'ordinary Home at launch')
    explorer_identity(unit_pid(unit), exe, out)
    arrange(scale, 'tester')
    pt = area(scale)

    def live_address(expected):
        key('KEY_LEFTALT', 'KEY_D')
        key('KEY_LEFTCTRL', 'KEY_C')
        actual = clipboard()
        key('KEY_ESC')
        assert actual.rstrip('/') == expected, (expected, actual)
        print(f'live address: {actual}', flush=True)

    def landing(name):
        check_landing(capture(out, name), pt)

    def expect(title, name):
        try:
            wait_for(lambda: captions() == [title], name, timeout=8)
        except AssertionError:
            capture(out, f'failed-{name}')
            print(f'{name}: expected {title}, got {captions()}', flush=True)
            raise

    home = capture(out, 'ordinary-home')
    assert 'Libraries' not in words(home, pt(170, 93) + pt(675, 254))
    live_address('/home/tester')
    click(pt(72, 197))
    expect('Libraries', 'pane-opens-landing-not-home')
    landing('libraries')
    live_address('win7-explorer:/libraries')
    if unavailable:
        # Leave a real forward entry, then remove Documents without refreshing Libraries.
        double_click(pt(465, 167))
        expect('Lab-Music', 'music-before-removal')
        key('KEY_LEFTALT', 'KEY_LEFT')
        expect('Libraries', 'landing-before-removal')
        docs = f'{base}/Custom-Docs'
        user(f'mv {docs} {docs}.held && test ! -e {docs} && test -r {base}')
        if unavailable == 'tile':
            double_click(pt(211, 167))
        else:
            click(pt(78, 216))
        warning = capture(out, f'missing-{unavailable}')
        titles = captions()
        print(f'missing {unavailable}: windows={titles}; removed {docs}', flush=True)
        assert sorted(titles) == ['Folder unavailable', 'Libraries'], titles
        message = words(warning, pt(158, 155) + pt(626, 248)).replace('\n', ' ')
        assert all(word in message for word in ('Cannot open', 'Custom-Docs')), message
        key('KEY_ESC')
        expect('Libraries', 'warning-dismissed-on-landing')
        landing('unchanged-landing')
        live_address('win7-explorer:/libraries')
        key('KEY_LEFTALT', 'KEY_RIGHT')
        expect('Lab-Music', 'forward-history-unchanged')
        live_address(f'{base}/Lab-Music')
        key('KEY_LEFTALT', 'KEY_LEFT')
        expect('Libraries', 'back-from-music')
        key('KEY_LEFTALT', 'KEY_LEFT')
        expect('tester', 'back-history-unchanged')
        live_address('/home/tester')
        # The child is also reachable from a normal folder, not just the overview.
        if unavailable == 'child':
            click(pt(78, 216))
            capture(out, 'missing-child-from-home')
            assert sorted(captions()) == ['Folder unavailable', 'tester'], captions()
            key('KEY_ESC')
            expect('tester', 'warning-dismissed-on-home')
            live_address('/home/tester')
            key('KEY_LEFTALT', 'KEY_RIGHT')
            expect('Libraries', 'forward-history-from-home-unchanged')
        user(f'mv {docs}.held {docs}')
        assert tree() == before, 'failed navigation changed files or XDG definitions'
        print(f'PASS: missing {unavailable} reported without changing view or history', flush=True)
        return
    for i, title in enumerate(FOLDERS):
        double_click(pt(211 + 254 * (i % 2), 167 + 56 * (i // 2)))
        expect(title, f'tile-{title}')
        live_address(f'{base}/{title}')
        capture(out, f'tile-{title}')
        key('KEY_LEFTALT', 'KEY_LEFT')
        expect('Libraries', 'back-from-' + title)
    for i, title in enumerate(FOLDERS):
        click(pt(78, 216 + 19 * i))
        expect(title, f'child-{title}')
        live_address(f'{base}/{title}')
        capture(out, f'child-{title}')
        key('KEY_LEFTALT', 'KEY_LEFT')
        expect('Libraries', f'back-from-child-{title}')
    landing('back-from-child')
    crumb = words(capture(out, 'libraries-crumb'), pt(111, 29) + pt(257, 52)).strip()
    assert crumb.split()[0] == 'Libraries', crumb
    key('KEY_LEFTALT', 'KEY_RIGHT')
    expect(FOLDERS[-1], 'forward-to-custom-videos')
    live_address(f'{base}/{FOLDERS[-1]}')
    address('/home/tester', 'tester')
    live_address('/home/tester')
    assert 'Libraries' not in words(capture(out, 'explicit-home'), pt(170, 93) + pt(675, 254))
    key('KEY_LEFTALT', 'KEY_LEFT')
    expect(FOLDERS[-1], 'back-from-explicit-home')
    key('KEY_LEFTALT', 'KEY_LEFT')
    expect('Libraries', 'history-libraries')
    landing('history-libraries')
    key('KEY_LEFTALT', 'KEY_RIGHT')
    expect(FOLDERS[-1], 'forward-from-libraries')
    key('KEY_LEFTALT', 'KEY_RIGHT')
    expect('tester', 'forward-home')
    live_address('/home/tester')

    # Both virtual destinations share a widget; neither must inherit the other's content.
    click(pt(68, 310))
    expect('Computer', 'computer-after-libraries')
    assert 'Storage volumes' in words(capture(out, 'computer'), pt(176, 94) + pt(450, 120))
    click(pt(72, 197))
    expect('Libraries', 'libraries-after-computer')
    landing('libraries-after-computer')
    key('KEY_F5')
    landing('libraries-refresh')
    assert tree() == before, 'browsing changed files or XDG definitions'
    (out / 'before-browsing.txt').write_text(before + '\n')
    (out / 'after-browsing.txt').write_text(tree() + '\n')

    docs = f'{base}/{FOLDERS[0]}'
    for folder, source, selected in ((sources, f'{sources}/IncludeMe', True),
                                     (f'{base}/IncludeCurrent', f'{base}/IncludeCurrent', False)):
        name = Path(source).name
        address(folder, Path(folder).name)
        if selected:
            click(pt(221, 150))
        image = capture(out, f'before-include-{name}')
        # The Open command precedes Include only with a selected item.
        band = words(image, pt(2, 59) + pt(414, 87)).replace('Includeinlibrary', 'Include in library')
        assert 'Include in library' in band and ('Open' in band) == selected, band
        click(pt(163 if selected else 114, 73))
        menu = capture(out, f'include-menu-{name}')
        menu_x = 166 if selected else 106
        menu_labels = words(menu, pt(menu_x, 90) + pt(menu_x + 73, 163))
        assert all(label in menu_labels for label in LABELS), menu_labels
        key('KEY_DOWN')
        key('KEY_ENTER')
        link = f'{docs}/{name}'
        wait_for(lambda: user(f'test -L {link} && readlink -f {link}', check=False) == source, f'{name} symlink')
        print(f'{name}: {user(f"ls -ld {link}")}', flush=True)
        capture(out, f'after-include-{name}')
    after = tree()
    links = [f'l {FOLDERS[0]}/{name} {source}' for name, source in
             (('IncludeMe', f'{sources}/IncludeMe'), ('IncludeCurrent', f'{base}/IncludeCurrent'))]
    remaining = after.splitlines()
    for link in links:
        remaining.remove(link)
    assert remaining == before.splitlines(), 'Include changed anything besides the two intended symlinks'
    (out / 'after-include.txt').write_text(after + '\n')
    print('PASS: four tiles, four children, Home/history, Computer isolation, unchanged contents and two folder links', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    parser.add_argument('--unavailable', choices=('tile', 'child'), help='exercise the missing Documents target')
    installed = parser.add_mutually_exclusive_group()
    installed.add_argument('--installed', action='store_true')
    installed.add_argument('--packaged', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not (args.installed or args.packaged):
        install(reset=False)
    output = output_name()
    base = user('mktemp -d /tmp/w7-libraries.XXXXXX')
    toggle('current', packaged=args.packaged)
    user(f'kscreen-doctor output.{output}.scale.{args.scale}')
    toggle('windows', packaged=args.packaged)
    try:
        run(args.out, args.scale, base, executable('win7-explorer', args.packaged), args.unavailable)
    finally:
        user(f'systemctl --user stop {Path(base).name}.service; rm -rf {base}')
        toggle('current', packaged=args.packaged)
        user(f'kscreen-doctor output.{output}.scale.1')


if __name__ == '__main__':
    main()
