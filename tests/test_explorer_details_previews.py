#!/usr/bin/env python3
"""Drive production Explorer at 100% with real KIO folder and file previews."""
import argparse
from base64 import b64encode
from io import BytesIO
from pathlib import Path
import shlex

from PIL import Image

from lab import VM, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, GEOMETRY, VIEW_MENU, captions, click, key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--explorer', default='/home/tester/.local/bin/win7-explorer',
                        help='absolute lab path to candidate or baseline; Classic style must already be installed')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    original = user('~/.local/bin/win7-classic status')
    assert original in ('current', 'windows'), original
    root = user('mktemp -d /tmp/w7-previews.XXXXXXXX')
    unit = Path(root).name
    folder = f'{root}/{unit}'
    cfg = f'{root}/config'
    plugins = '[PreviewSettings]\nPlugins=directorythumbnail,imagethumbnail'

    def write_png(path, color):
        png = BytesIO()
        Image.new('RGB', (256, 256), color).save(png, format='PNG')
        user(f'echo {b64encode(png.getvalue()).decode()} | base64 -d > {path}')

    def place():
        kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" '
                    f'&& w.caption == "{unit}") {{ w.frameGeometry = {GEOMETRY}; workspace.activeWindow = w; }}')
        vmctl.pointer(VM, 1100, 700)

    def sample(tag, box):
        path = args.out / f'{tag}.png'
        shot(path)
        with Image.open(path) as image:
            assert image.size == (1280, 800), image.size
            crop = image.convert('RGB').crop(box)
        pixels = crop.get_flattened_data()
        magenta = sum(r > 165 and g < 90 and b > 150 for r, g, b in pixels)
        cyan = sum(r < 90 and g > 165 and b > 165 for r, g, b in pixels)
        return magenta, cyan

    def choose(up):
        click(VIEW_MENU)
        for _ in range(up):
            key('KEY_UP')
        key('KEY_ENTER')
        vmctl.pointer(VM, 1100, 700)

    # Non-overlapping crop boxes at native geometry exclude the preview pane, menus and other columns.
    large = (435, 212, 658, 320)
    first_row = (433, 237, 456, 260)
    details = (432, 234, 456, 288)
    try:
        user(f'mkdir -p {cfg} {folder}/AFolder; ln -s "$HOME/.config/kdeglobals" {cfg}/kdeglobals; '
             f'printf "%s\\n" {shlex.quote(plugins)} > {cfg}/dolphinrc')
        write_png(f'{folder}/AFolder/Magenta.png', 'magenta')
        write_png(f'{folder}/Cyan.png', 'cyan')
        toggle('windows')
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={cfg} '
             f'--setenv=XDG_CACHE_HOME={root}/cache --setenv=LC_ALL=en_US.UTF-8 '
             f'{shlex.quote(args.explorer)} {folder}')
        wait_for(lambda: unit in captions(), 'production preview fixture')
        place()
        wait_for(lambda: min(sample('large-previews', large)) > 16, 'real folder and file previews in Large Icons')
        choose(3)  # Details; the folder thumbnail is already in KIO's directory model.
        wait_for(lambda: sample('classic-details', details)[1] > 16, 'standalone PNG preview still present in Details')
        magenta, cyan = sample('classic-details', details)
        assert magenta == 0 and cyan > 16, (magenta, cyan)
        with Image.open(args.out / 'classic-details.png') as image:
            colors = image.convert('RGB').crop(first_row).get_flattened_data()
        assert any(r > 140 and g > 110 and b < g - 25 for r, g, b in colors), 'folder icon disappeared'

        # No reload or relaunch: the same Details window must restore its ordinary KDE previews.
        pid_command = f'systemctl --user show -p MainPID --value {unit}'
        pid = user(pid_command)
        toggle('current')
        place()
        wait_for(lambda: min(sample('current-details', (432, 228, 460, 304))) > 4,
                 'the same Current-mode Details window restores both previews')
        toggle('windows')
        place()
        wait_for(lambda: sample('classic-details-again', details)[0] == 0, 'Classic suppression resumes live')
        assert sample('classic-details-again', details)[1] > 16
        assert pid == user(pid_command) and int(pid) > 0, 'Explorer restarted during the switch'
        choose(7)  # Large Icons, with the same saved thumbnail preference.
        wait_for(lambda: min(sample('large-restored', large)) > 16, 'both previews return outside Details')
        assert user(f'test ! -e {cfg}/win7-explorer-optionsrc && cat {cfg}/dolphinrc') == plugins, 'preview policy wrote settings'
        print('PASS: only the folder thumbnail is suppressed in Classic Details; round trips restore both previews')
    finally:
        user(f'systemctl --user stop {unit} || true; rm -r {root}')
        if user('~/.local/bin/win7-classic status') != original:
            toggle(original)


if __name__ == '__main__':
    main()
