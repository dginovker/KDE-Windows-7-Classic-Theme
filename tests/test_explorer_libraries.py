#!/usr/bin/env python3
"""Drive the Libraries landing page, XDG overrides, ordinary Home and history."""
import argparse
from pathlib import Path

from lab import install, toggle, user, wait_for
from test_explorer import captions, click, key
from test_explorer_command_menus import words
from test_explorer_computer import address, area, arrange, capture
from test_upgrade import output_name


def run(out, scale, base):
    cfg = f'{base}/config'
    user(f'mkdir -p {cfg} {base}/Custom-Docs {base}/Lab-Music {base}/Lab-Pictures {base}/Lab-Videos; '
         f'cp ~/.config/kdeglobals {cfg}/; '
         f'printf \'XDG_DOCUMENTS_DIR="{base}/Custom-Docs"\nXDG_MUSIC_DIR="{base}/Lab-Music"\n'
         f'XDG_PICTURES_DIR="{base}/Lab-Pictures"\nXDG_VIDEOS_DIR="{base}/Lab-Videos"\n\' > {cfg}/user-dirs.dirs; '
         f'systemd-run --user --collect -q --setenv=XDG_CONFIG_HOME={cfg} ~/.local/bin/win7-explorer ~')
    wait_for(lambda: captions() == ['tester'], 'ordinary Home at launch')
    arrange(scale, 'tester')
    pt = area(scale)

    def body(name):
        return words(capture(out, name), pt(170, 93) + pt(675, 254))

    def landing(name):
        labels = body(name)
        assert all(word in labels for word in ('Libraries', 'Documents', 'Music', 'Pictures', 'Videos')), labels
        assert labels.count('Library') == 4, labels

    assert 'Libraries' not in body('ordinary-home')
    click(pt(72, 197))
    wait_for(lambda: captions() == ['Libraries'], 'pane opens landing, not Home')
    landing('libraries')
    for i, title in enumerate(('Custom-Docs', 'Lab-Music', 'Lab-Pictures', 'Lab-Videos')):
        click(pt(211 + 254 * (i % 2), 167 + 56 * (i // 2)))
        if 'Libraries' in captions():
            key('KEY_ENTER')
        wait_for(lambda: captions() == [title], f'tile opens configured location: {title}')
        capture(out, f'tile-{title}')
        key('KEY_LEFTALT', 'KEY_LEFT')
        wait_for(lambda: captions() == ['Libraries'], 'Back restores namespace')
    click(pt(78, 216))
    wait_for(lambda: captions() == ['Custom-Docs'], 'Documents child uses the same customized path')
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: captions() == ['Libraries'], 'Back from customized child')
    landing('back-from-child')
    key('KEY_LEFTALT', 'KEY_RIGHT')
    wait_for(lambda: captions() == ['Custom-Docs'], 'Forward to customized child')
    address('/home/tester', 'tester')
    assert 'Libraries' not in body('explicit-home'), 'explicit Home displayed a Libraries landing page'
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: captions() == ['Custom-Docs'], 'Back from explicit Home')
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: captions() == ['Libraries'], 'Libraries retained across normal Home history')
    landing('history-libraries')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    parser.add_argument('--installed', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.installed:
        install(reset=False)
    output = output_name()
    base = user('mktemp -d /tmp/w7-libraries.XXXXXX')
    toggle('current')
    user(f'kscreen-doctor output.{output}.scale.{args.scale}')
    toggle('windows')
    try:
        run(args.out, args.scale, base)
    finally:
        user(f'pkill -x win7-explorer || true; rm -rf {base}')
        toggle('current')
        user(f'kscreen-doctor output.{output}.scale.1')


if __name__ == '__main__':
    main()
