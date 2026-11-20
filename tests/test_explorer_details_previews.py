#!/usr/bin/env python3
"""Exercise packaged Explorer with real KIO previews in the disposable lab."""
import argparse
from base64 import b64encode
from io import BytesIO
from pathlib import Path
import shlex
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, explorer_identity, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    parser.add_argument('--check', choices=('all', 'mode', 'cut', 'missing-icon'), default='all')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    check = args.check
    tool = '/usr/bin/win7-classic'
    executable = '/usr/bin/win7-explorer'
    original = user(f'{tool} status')
    assert original == 'current', original
    root = user('mktemp -d /tmp/w7-previews.XXXXXXXX')
    unit = Path(root).name
    folder = f'{root}/{unit}'
    cfg = f'{root}/config'
    plugins = '[PreviewSettings]\nPlugins=directorythumbnail,imagethumbnail'
    appearance_files = ('"${XDG_CONFIG_HOME:-$HOME/.config}/kdeglobals" '
                        '"${XDG_STATE_HOME:-$HOME/.local/state}/win7-classic/profiles/current/keys.json"')
    snapshot = False
    x, y = (256, 120) if args.scale == 1 else (42, 24)
    s = args.scale

    def pt(a, b):
        return round((x + a) * s), round((y + b) * s)

    def write_png(path, color):
        png = BytesIO()
        Image.new('RGB', (256, 256), color).save(png, format='PNG')
        user(f'echo {b64encode(png.getvalue()).decode()} | base64 -d > {path}')

    def place():
        kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" '
                    f'&& w.caption == "{unit}") {{ w.frameGeometry = {{x:{x}, y:{y}, width:768, height:{560 if s == 1 else 460}}}; '
                    'workspace.activeWindow = w; }')
        vmctl.pointer(VM, 1230, 660 if s == 1 else 740)

    def snap(tag):
        path = args.out / f'{tag}.png'
        shot(path)
        with Image.open(path) as image:
            assert image.size == (1280, 800), image.size
            return image.convert('RGB')

    def crop(image, box):
        return image.crop((*pt(*box[:2]), *pt(*box[2:])))

    def sample(tag, box):
        pixels = crop(snap(tag), box).get_flattened_data()
        magenta = sum(r > 165 and g < 90 and b > 150 for r, g, b in pixels)
        cyan = sum(r < 90 and g > 165 and b > 165 for r, g, b in pixels)
        return magenta, cyan

    def choose(up):
        click(pt(686, 74))
        for _ in range(up):
            vmctl.keys(VM, 'KEY_UP')
        key('KEY_ENTER')
        vmctl.pointer(VM, 1230, 740)

    def launch():
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={cfg} '
             f'--setenv=XDG_CACHE_HOME={root}/cache --setenv=LC_ALL=en_US.UTF-8 {executable} {folder}')
        wait_for(lambda: unit in captions(), 'production preview fixture')
        place()
        pid = user(f'systemctl --user show -p MainPID --value {unit}')
        explorer_identity(pid, executable, args.out)
        return pid

    def options(enabled):
        click(pt(70, 74))  # Organize dropdown
        key('KEY_F')
        wait_for(lambda: 'Folder Options' in captions(), 'Folder Options opened')
        key('KEY_LEFTALT', 'KEY_V')
        key('KEY_LEFTALT', 'KEY_T')
        snap(f'options-{enabled}-{time.monotonic_ns()}')
        key('KEY_ENTER')
        wait_for(lambda: 'Folder Options' not in captions(), 'Folder Options accepted')
        assert user(f'kreadconfig6 --file {cfg}/win7-explorer-optionsrc --group View --key Thumbnails') == str(enabled).lower()

    large = (179, 92, 402, 200)
    details = (176, 114, 200, 168)
    current_details = (176, 108, 204, 184)

    def ink(image):
        bounds = ImageChops.difference(image, Image.new('RGB', image.size, 'white')).getbbox()
        assert bounds, 'folder icon missing'
        return image.crop(bounds)

    native = ink(Image.open(ROOT / 'reference/screenshots/w7-explorer-details.png').convert('RGB')
                .crop((430, 238, 455, 259)))
    icon_box = (177, 117, 200, 143)

    def plain(tag):
        wait_for(lambda: sample(tag, details)[1] > 16, 'standalone PNG preview still present in Details')
        magenta, cyan = sample(tag, details)
        print(f'{tag}: magenta={magenta}, cyan={cyan}', flush=True)
        assert magenta == 0 and cyan > 16, (magenta, cyan)
        icon = ink(crop(snap(tag), icon_box))
        if s == 1:
            assert icon == native, 'normal folder glyph differs from genuine Windows 7'
        else:
            assert all(abs(actual - expected * s) <= 2 for actual, expected in zip(icon.size, native.size)), icon.size
            assert sum(r > 140 and g > 110 and b < g - 25 for r, g, b in icon.get_flattened_data()) > 100

    def folder_cut():
        before = crop(snap('before-cut'), icon_box)
        click(pt(218, 131))
        key('KEY_LEFTCTRL', 'KEY_X')
        click(pt(360, 395))  # Measure the cut treatment without selection highlight.
        after = crop(snap('after-cut'), icon_box)
        pixels = list(zip(before.get_flattened_data(), after.get_flattened_data()))
        faded = sum(sum(b) > sum(a) + 30 for a, b in pixels)
        print(f'Ctrl+X: {faded} folder-icon pixels faded', flush=True)
        assert faded > 50 and sum(sum(b) < sum(a) - 6 for a, b in pixels) == 0, 'cut folder is not dimmed'
        assert sum(p != (255, 255, 255) for p in after.get_flattened_data()) > 50, 'cut icon disappeared'
        user(f'mkdir {folder}/ZDestination')
        key('KEY_LEFTALT', 'KEY_D')
        vmctl.type_text(VM, f'{folder}/ZDestination\n')
        wait_for(lambda: 'ZDestination' in captions(), 'open destination in Explorer')
        key('KEY_LEFTCTRL', 'KEY_V')
        wait_for(lambda: user(f'test -f {folder}/ZDestination/AFolder/Magenta.png && test ! -e {folder}/AFolder && echo moved')
                 == 'moved', 'Ctrl+V really moves the image-filled folder')
        key('KEY_LEFTCTRL', 'KEY_Z')
        wait_for(lambda: user(f'test -f {folder}/AFolder/Magenta.png && test ! -e {folder}/ZDestination/AFolder && echo undone')
                 == 'undone', 'Ctrl+Z restores the moved folder')
        print('Cut folder moved through real paste and was restored through Undo', flush=True)
        key('KEY_LEFTALT', 'KEY_LEFT')
        wait_for(lambda: unit in captions(), 'return to the source listing')
        place()
        user(f'rmdir {folder}/ZDestination')
        plain('cut-undo-restored')

    def missing_icon():
        # KIO falls back to its regular unknown icon, not the folder art and not a blank space.
        user(f'mkdir {root}/DMissing {root}/EUnknown; '
             f'printf "[Desktop Entry]\\nIcon=w7-no-such-theme-icon\\n" > {root}/DMissing/.directory; '
             f'printf "[Desktop Entry]\\nIcon=unknown\\n" > {root}/EUnknown/.directory; '
             f'mv {root}/DMissing {root}/EUnknown {folder}/')
        wait_for(lambda: sample('missing-icon-listing', (176, 166, 200, 210))[1] > 16, 'custom-icon folders listed')
        image = snap('missing-icon-listing')
        missing, unknown = [crop(image, (177, 123 + 22*n, 200, 140 + 22*n)) for n in (1, 2)]
        assert ink(missing) == ink(unknown), 'missing custom icon differs from the stock unknown icon'
        user(f'rm -r {folder}/DMissing {folder}/EUnknown')
        print('Missing custom icon resolves to the stock unknown icon', flush=True)

    try:
        user(f'mkdir -p {cfg} {folder}/AFolder; ln -s "$HOME/.config/kdeglobals" {cfg}/kdeglobals; '
             f'printf "%s\\n" {shlex.quote(plugins)} > {cfg}/dolphinrc')
        if check in ('all', 'mode'):
            # Switching saves the forced style to the Current profile as well as the live config.
            user(f'set -eu; for file in {appearance_files}; do '
                 f'if test -e "$file"; then cp -p "$file" "{root}/original-${{file##*/}}"; fi; done')
            snapshot = True
            user('kwriteconfig6 --file kdeglobals --group KDE --key widgetStyle Win7Classic')
        write_png(f'{folder}/AFolder/Magenta.png', 'magenta')
        write_png(f'{folder}/Cyan.png', 'cyan')
        user(f'kscreen-doctor output.Virtual-1.scale.{s}')
        time.sleep(2)
        toggle('windows', packaged=True)
        pid = launch()
        wait_for(lambda: min(sample('large-previews', large)) > 16, 'real folder and file previews in Large Icons')
        print('Large Icons: both real previews', flush=True)
        choose(3)
        plain('classic-details')

        if check in ('all', 'mode'):
            def verify_style(mode):
                assert user(f'{tool} status') == mode
                assert user('kreadconfig6 --file kdeglobals --group KDE --key widgetStyle').lower() == 'win7classic'
                assert 'libwin7classicstyle.so' in user(f'grep -m1 libwin7classicstyle.so /proc/{pid}/maps')
                print(f'{mode}: same Explorer PID {pid} and Win7Classic widget style', flush=True)

            verify_style('windows')
            toggle('current', packaged=True)
            place()
            verify_style('current')
            wait_for(lambda: min(sample('current-details', current_details)) > 4,
                     'the same Current-mode Details window restores both previews')
            print('Current Details: both previews with the same live model and widget style', flush=True)
            toggle('windows', packaged=True)
            place()
            plain('classic-details-again')
            assert pid == user(f'systemctl --user show -p MainPID --value {unit}') and int(pid) > 0
            assert user(f'test ! -e {cfg}/win7-explorer-optionsrc && cat {cfg}/dolphinrc') == plugins
        if check in ('all', 'cut'):
            folder_cut()
        if check in ('all', 'missing-icon'):
            missing_icon()
        if check != 'all':
            print(f'PASS {s:g}x: {check}', flush=True)
            return

        click(pt(712, 74))  # Separate Preview pane
        click(pt(360, 395))  # Focus Details without activating any file.
        key('KEY_HOME')
        key('KEY_DOWN')  # Select the standalone PNG without opening it.
        panel = (455, 109, 757, 401)
        wait_for(lambda: sample('preview-pane', panel)[1] > 500, 'KIO preview pane displays the selected image')
        click(pt(712, 74))
        wait_for(lambda: sample('preview-closed', panel)[1] == 0, 'Preview pane closes independently')
        click(pt(360, 395))  # Clear PNG selection before comparing the unselected folder glyph.
        options(False)
        wait_for(lambda: sample('details-disabled', details) == (0, 0), 'user preference disables file thumbnail')
        options(True)
        plain('details-enabled')
        choose(7)
        wait_for(lambda: min(sample('large-restored', large)) > 16, 'both previews restore in Large Icons')
        options(False)
        wait_for(lambda: sample('large-disabled', large) == (0, 0), 'thumbnail preference also disables both Large Icons previews')
        options(True)
        wait_for(lambda: min(sample('large-enabled', large)) > 16, 'thumbnail preference restores Large Icons previews')
        choose(6)
        wait_for(lambda: min(sample('medium-enabled', large)) > 16, 'Medium Icons keeps folder and file previews')
        choose(3)
        plain('details-from-medium')
        user(f'systemctl --user stop {unit}')
        launch()
        plain('remembered-details')

        # Keep the two overlay rows separate from the file thumbnail; do not compare whole screenshots.
        user(f'ln -s AFolder {folder}/BLinked; mkdir -m 000 {folder}/CLocked')
        wait_for(lambda: sample('details-overlays', (176, 166, 200, 212))[1] > 16, 'all mixed-listing rows visible')
        image = snap('details-overlays')
        a, b, c = [crop(image, (178, 121 + 22*n, 197, 137 + 22*n)) for n in range(3)]
        assert ImageChops.difference(a, b).getbbox(), 'symlink overlay missing'
        assert ImageChops.difference(a, c).getbbox(), 'locked folder overlay missing'
        assert user(f'cat {cfg}/dolphinrc') == plugins
        print(f'PASS {s:g}x: packaged Explorer, standalone and pane thumbnails, live policy, options, other views and folder overlays')
    finally:
        try:
            user(f'systemctl --user stop {unit} || true')
            if user(f'{tool} status') != original:
                toggle(original, packaged=True)
        finally:
            if snapshot:
                print(user(f'''set -eu
for file in {appearance_files}; do
    backup="{root}/original-${{file##*/}}"
    if test -f "$backup"; then
        cp -p "$backup" "$file"
        cmp "$backup" "$file"
        echo "Cleanup verified: $file restored byte-for-byte"
    else
        rm -f "$file"
        test ! -e "$file" && test ! -L "$file" || exit 1
        echo "Cleanup verified: $file remains absent"
    fi
done
dbus-send --session --type=signal /KGlobalSettings org.kde.KGlobalSettings.notifyChange int32:2 int32:0
'''), flush=True)
            user(f'set -eu; if test -d {folder}/CLocked; then chmod u+rwx {folder}/CLocked; fi; rm -r {root}; '
                 'kscreen-doctor output.Virtual-1.scale.1')


if __name__ == '__main__':
    main()
