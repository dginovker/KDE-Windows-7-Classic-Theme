#!/usr/bin/env python3
"""Drive real Explorer windows and check both Classic taskbar icon roles (#48)."""
from pathlib import Path
import sys
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, install, kwin_query, shot, toggle, user, vmctl, wait_for
from test_upgrade import output_name

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-explorer-task-icon')
REF = ROOT / 'reference/screenshots/w7-explorer-jumplist.png'
APP = 'org.win7classic.explorer'
FACE = (212, 208, 200)
WHITE = (255, 255, 255)


def crop(path, xy, size):
    x, y = xy
    return Image.open(path).convert('RGB').crop((x, y, x + size, y + size))


def asset(name, size):
    return Image.open(ROOT / f'explorer/assets/{name}-{size}.png').convert('RGBA')


def composite(icon, face):
    base = Image.new('RGBA', icon.size, face + (255,))
    base.alpha_composite(icon)
    return base.convert('RGB')


def channel_errors(actual, expected):
    return [max(rgb) for rgb in ImageChops.difference(actual, expected).get_flattened_data()]


def compare(actual, expected, icon, description):
    errors = channel_errors(actual, expected)
    solid = max(delta for delta, a in zip(errors, icon.getchannel('A').get_flattened_data()) if a in (0, 255))
    mean = sum(errors) / len(errors)
    # KWin/Qt's window-icon transfer composites some fractional-alpha edge pixels differently.
    # Keep both the solid pixels and the whole region (every edge pixel included) accountable.
    assert solid <= 2 and mean <= 3, f'{description}: solid max {solid}, full-region mean {mean:.2f}'
    print(f'{description}: solid max {solid}/255, full-region mean {mean:.2f}/255')


def expect_icon(path, xy, name, face, size=32):
    icon = asset(name, size)
    compare(crop(path, xy, size), composite(icon, face), icon, f'{path.name}: {name}-{size}')


def check_native(path, xy, face):
    # Compare every pixel, including the antialiased edge and shadow. Translate only the background
    # contribution using the existing transparent imageres.dll folder asset, not a KDE golden.
    native = crop(REF, (117, 763), 32)
    icon = asset('folder', 32)
    on_white = composite(icon, WHITE)
    on_face = composite(icon, face)
    expected = Image.frombytes('RGB', native.size, bytes(max(0, min(255, n + f - w)) for n, f, w in
                               zip(native.tobytes(), on_face.tobytes(), on_white.tobytes())))
    actual = crop(path, xy, 32)
    actual.save(OUT / f'{path.stem}-32.png')
    expected.save(OUT / f'{path.stem}-native-32.png')
    compare(actual, expected, icon, f'{path.name}: native 32px folder icon')


def explorer_windows():
    return kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass === "{APP}") '
                      'emit(w.internalId, w.caption, w.active);')


def capture(name):
    time.sleep(0.7)
    path = OUT / f'{name}.png'
    shot(path)
    return path


def launch(where):
    user(f'systemd-run --user --collect -q ~/.local/bin/win7-explorer {where}')


def navigate(where, caption, window):
    vmctl.keys(VM, 'KEY_LEFTALT', 'KEY_D')
    vmctl.type_text(VM, where + '\n')
    wait_for(lambda: [window, caption, 'true'] in explorer_windows(), f'same Explorer window navigated to {caption}')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    output = output_name()
    user(f'kscreen-doctor output.{output}.scale.1')
    user('mkdir -p ~/Classic-demo ~/Downloads')
    user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "for (const w of panels()[0].widgets()) '
         'if (w.type == \\"org.kde.plasma.icontasks\\") { w.currentConfigGroup = [\\"General\\"]; '
         'w.writeConfig(\\"launchers\\", [\\"applications:org.kde.kate.desktop\\", \\"applications:org.kde.dolphin.desktop\\", '
         '\\"applications:org.kde.konsole.desktop\\"]); }"')
    toggle('windows')
    try:
        vmctl.pointer(VM, 640, 695)
        pinned = capture('100-pinned')
        launch('~/Classic-demo')
        wait_for(lambda: len(explorer_windows()) == 1, 'first Explorer window')
        ordinary = capture('100-ordinary')
        check_native(ordinary, (117, 764), WHITE)
        expect_icon(pinned, (121, 763), 'explorer', FACE)
        assert crop(pinned, (71, 763), 32) == crop(ordinary, (71, 763), 32), 'neighboring Kate pin changed'

        vmctl.pointer(VM, 190, 778, 'right')
        vmctl.pointer(VM, 640, 695)
        menu = capture('100-jumplist')
        assert crop(menu, (87, 680), 16) == crop(REF, (87, 680), 16), 'jump-list launch icon is not native'
        check_native(menu, (117, 764), WHITE)
        vmctl.keys(VM, 'KEY_ESC')
        if explorer_windows()[0][2] != 'true':
            vmctl.pointer(VM, 190, 778, 'left')
        vmctl.pointer(VM, 640, 695)

        first = explorer_windows()[0][0]
        navigate('/home/tester/Downloads', 'Downloads', first)
        expect_icon(capture('100-downloads'), (117, 764), 'downloads', WHITE)
        navigate('/home/tester/Classic-demo', 'Classic-demo', first)
        check_native(capture('100-back-to-ordinary'), (117, 764), WHITE)

        launch('~/Downloads')
        wait_for(lambda: len(explorer_windows()) == 2, 'second Explorer window')
        simultaneous = capture('100-two-windows')
        expect_icon(simultaneous, (116, 763), 'folder', FACE)
        expect_icon(simultaneous, (279, 764), 'downloads', WHITE)
        vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: [first, 'Classic-demo', 'true'] in explorer_windows(), 'first window active after closing second')
        check_native(capture('100-after-close'), (117, 764), WHITE)
        vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_W')
        wait_for(lambda: not explorer_windows(), 'both windows closed')
        expect_icon(capture('100-after-last-close'), (121, 763), 'explorer', FACE)

        user(f'kscreen-doctor output.{output}.scale.1.5')
        time.sleep(2)
        expect_icon(capture('150-pinned'), (182, 744), 'explorer', FACE, 48)
        launch('~/Classic-demo')
        wait_for(lambda: len(explorer_windows()) == 1, 'new Explorer window at 150%')
        reopened = capture('150-reopened')
        # The compositor samples this 32-logical-pixel icon at a fractional origin at 150%.
        # Check the full 48-device-pixel region against the genuine 48px art, not an exact raster golden.
        actual = crop(reopened, (177, 746), 48)
        errors = channel_errors(actual, composite(asset('folder', 48), WHITE))
        mean = sum(errors) / len(errors)
        assert mean <= 14, f'150% reopened Explorer task is not the folder icon (mean channel delta {mean:.2f})'
        print(f'150% reopened folder: 48px full-region mean {mean:.2f}/255')
        print('Explorer task icon checks passed at 100% and 150%')
    finally:
        user('pkill -x win7-explorer || true')
        user(f'kscreen-doctor output.{output}.scale.1')
        toggle('current')


if __name__ == '__main__':
    main()
