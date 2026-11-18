#!/usr/bin/env python3
"""Switch and resize a real empty Explorer view against Windows 7 (issue #41)."""
import argparse
import json
from pathlib import Path
import shlex

from PIL import Image

from lab import ROOT, VM, install, kwin_query, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, key

WHITE = (255, 255, 255)
NATIVE = ROOT / 'reference/screenshots'


def guest_file(path, nonempty=False):
    flag = '-s' if nonempty else '-f'
    return user(f'if test {flag} {shlex.quote(path)}; then echo yes; else echo no; fi') == 'yes'


def unit_running(unit):
    service = shlex.quote(unit + '.service')
    return bool(user('systemctl --user list-units --no-legend --plain '
                     f'--state=active,activating,deactivating,reloading {service}'))


def stop_unit(unit):
    if unit_running(unit):
        user(f'systemctl --user stop {shlex.quote(unit)}')
    assert not unit_running(unit), f'fixture unit is still running: {unit}'


def ink(image):
    return image.convert('L').point(lambda n: 255 if n < 140 else 0).getbbox()


def position(image, left, top, right, scale):
    center = (left + right) / 2
    half = round(75 * scale)
    start = round(center) - half
    box = ink(image.crop((start, top, start + half * 2, top + round(45 * scale))))
    assert box, f'no empty-message ink below content edge at y={top}'
    x0, y0, x1, y1 = box
    return ((start + (x0 + x1) / 2 - center) / scale, y0 / scale, (x1 - x0) / scale, (y1 - y0) / scale)


def exercise(out, scale, root):
    out.mkdir(parents=True, exist_ok=True)
    unit = f'{Path(root).name}-{round(scale * 100)}'
    user(f'mkdir -p {root}/Classic-demo/Documents {root}/config-{scale}; '
         f'cp ~/.config/kdeglobals {root}/config-{scale}/')
    place = (256, 120, 768, 560) if scale == 1 else (42, 45, 730, 405)
    x, y, w, h = place
    match = f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}")'

    def point(x, y):
        return round(x * scale), round(y * scale)

    def launch(unit, url, caption):
        user(f'systemd-run --user --collect -q --unit={unit} --setenv=XDG_CONFIG_HOME={root}/config-{scale} '
             f'~/.local/bin/win7-explorer {shlex.quote(url)}')
        wait_for(lambda: caption in captions(), f'Explorer at {caption}')
        focus(caption)
        assert geometry() == place

    def focus(caption):
        kwin_script(match + f' if (w.caption == {json.dumps(caption)}) {{ '
                    f'w.frameGeometry = {{x:{x}, y:{y}, width:{w}, height:{h}}}; workspace.activeWindow = w; }}')

    def geometry():
        (row,) = kwin_query(match + ' if (workspace.activeWindow == w) { '
                            'const g = w.frameGeometry; emit(g.x, g.y, g.width, g.height); }')
        return tuple(int(float(n)) for n in row)

    def go(url, caption):
        key('KEY_LEFTALT', 'KEY_D')
        vmctl.type_text(VM, url + '\n')
        wait_for(lambda: caption in captions(), f'navigated to {caption}')

    def view(index):
        _, _, width, _ = geometry()
        click(point(x + width - 82, y + 74))
        # Use the command-bar order; the separate background submenu below still ends with Details.
        for _ in range({'details': 6, 'list': 5, 'icons': 2}[index]):
            key('KEY_DOWN')
        key('KEY_ENTER')

    def snapshot(tag, ready=None):
        vmctl.pointer(VM, 1180, 710)
        path = out / f'{tag}.png'
        image = None

        def capture():
            nonlocal image
            shot(path)
            with Image.open(path) as frame:
                assert frame.size == (1280, 800), frame.size
                image = frame.convert('RGB')
            return ready is None or ready(image)

        wait_for(capture, f'observable {tag} (last frame: {path})')
        return image

    def content(image, mode, width):
        left, y0 = point(x + 164, y + 90)
        right = point(x + width - 4, 0)[0]
        # Probe blank space in a column heading, not any text, divider or item.
        probe = point(x + 164 + 175, y + 102)
        if (image.getpixel(probe) == WHITE) != (mode != 'details'):
            return None
        if mode == 'details':
            top = next((row for row in range(probe[1], y0 + round(28 * scale))
                        if image.getpixel((probe[0], row)) == WHITE), None)
            if top is None:
                return None
            assert abs((top - y0) / scale - 23) <= 1, (y0, top)
        else:
            top = y0
        return left, top, right

    def empty(tag, mode):
        _, _, width, _ = geometry()

        def label_visible(image):
            bounds = content(image, mode, width)
            if bounds:
                left, top, right = bounds
                center = (left + right) // 2
                return ink(image.crop((center - round(75 * scale), top,
                                       center + round(75 * scale), top + round(45 * scale))))
            return False

        image = snapshot(tag, label_visible)
        left, top, right = content(image, mode, width)
        actual = position(image, left, top, right, scale)
        oracle = 'details' if mode == 'details' else 'icons'
        with Image.open(NATIVE / f'w7-explorer-empty-{oracle}.png') as native:
            target = position(native, 0, 23 if mode == 'details' else 0, native.width, 1)
        print(f'{scale:g}x {tag}: content=({left},{top},{right}), '
              f'ink (center delta, gap, width, height)={actual}, native={target}', flush=True)
        assert abs(actual[0] - target[0]) <= 3, f'{tag}: empty-message not centered'
        assert abs(actual[1] - target[1]) <= 2, f'{tag}: wrong gap below content/header'
        assert abs(actual[2] - target[2]) <= 6 and abs(actual[3] - target[3]) <= 2, f'{tag}: clipped or wrong text'
        center = (left + right) // 2
        # Return an actual foreground pixel for right-clicking the label itself.
        for row in range(top + round(15 * scale), top + round(33 * scale)):
            for col in range(center - round(40 * scale), center + round(40 * scale)):
                if max(image.getpixel((col, row))) < 100:
                    return col, row
        raise AssertionError(f'{tag}: missing foreground ink')

    def populated(tag):
        _, _, width, _ = geometry()

        def first_row(image):
            bounds = content(image, 'details', width)
            if bounds is None:
                return None
            left, top, _ = bounds
            return image.crop((left, top, left + round(130 * scale), top + round(46 * scale)))

        image = snapshot(tag, lambda image: (rows := first_row(image)) is not None and ink(rows))
        left, top, right = content(image, 'details', width)
        middle = (left + right) // 2
        # Sample the start of the message, clear of the file name and Date modified cell.
        message_start = (middle - round(52 * scale), top, min(middle, left + round(272 * scale)), top + round(45 * scale))
        assert not ink(image.crop(message_start)), 'empty label survived'
        return first_row(image).tobytes()

    def icon_ink(image):
        return ink(image.crop((*point(x + 175, y + 105), *point(x + 269, y + 206))))

    def resize(dx, dy):
        _, _, width, height = geometry()
        vmctl.pointer(VM, *point(x + width - 2, y + height - 2))
        vmctl.button(VM, 'left', True)
        try:
            vmctl.pointer(VM, *point(x + width - 2 + dx, y + height - 2 + dy))
        finally:
            vmctl.button(VM, 'left', False)

        def resized():
            _, _, new_width, new_height = geometry()
            return abs(new_width - width - dx) <= 2 and abs(new_height - height - dy) <= 2

        wait_for(resized, f'drag resize {width}x{height} by ({dx},{dy})')

    def webdav():
        server = f'{unit}-dav'
        source = Path(__file__).with_name('fixture_explorer_webdav.py').read_text()
        user(f'printf %s {shlex.quote(source)} > {root}/dav.py && '
             f'systemd-run --user --collect -q --unit={server} python {root}/dav.py {root}')

        def marker(name, event):
            wait_for(lambda: guest_file(f'{root}/{name}.{event}'), f'DAV {name} {event}')

        def release(name):
            user(f'touch {root}/{name}.release')
            marker(name, 'responded')

        def open_dav(name):
            go(f'webdav://127.0.0.1:{port}/{name}/', name)
            marker(name, 'requested')

        def no_label(tag, ready=None):
            image = snapshot(tag, ready)
            left, top, right = content(image, 'icons', w)
            center = (left + right) // 2
            box = ink(image.crop((center - 62, top, center + 62, top + 42)))
            print(f'1x {tag}: label ink={box}', flush=True)
            assert box is None, f'{tag}: falsely said folder was empty'
            return image

        try:
            wait_for(lambda: guest_file(f'{root}/port', nonempty=True), 'loopback DAV ready')
            port = int(user(f'cat {root}/port'))
            open_dav('Slow')
            no_label('slow-pending')
            release('Slow')
            no_label('slow-populated', icon_ink)
            user(f'rm {root}/Slow.{{requested,release,responded}}')
            key('KEY_F5')
            marker('Slow', 'requested')
            no_label('relist-pending')
            release('Slow')
            no_label('relist-populated', icon_ink)
            open_dav('Superseded')
            no_label('superseded-pending')
            open_dav('Final')
            release('Superseded')
            no_label('final-still-pending')
            release('Final')
            empty('final-completed-empty', 'icons')
            open_dav('Failed')
            no_label('failed-pending')
            release('Failed')
            wait_for(lambda: 'Error' in captions(), 'KIO error dialog for unsuccessful listing')
            snapshot('failed-result')
            key('KEY_ESC')
            wait_for(lambda: 'Error' not in captions(), 'dismissed the KIO error dialog')
            no_label('failed-dismissed')
            key('KEY_LEFTALT', 'KEY_LEFT')
            wait_for(lambda: 'Final' in captions(), 'back to successfully listed empty folder')
            empty('back-to-final-empty', 'icons')
        finally:
            stop_unit(server)

    def root_identity():
        other_unit = f'{unit}-root'
        user(f'mkdir -p {root}/identity/{{existing,Direct,Open}}; : > {root}/identity/Open/Sample.txt')
        try:
            launch(other_unit, f'file://{root}/identity/existing/../Direct/', 'Direct')
            empty('direct-dot-segment-root', 'icons')
            key('KEY_LEFTCTRL', 'KEY_W')
            wait_for(lambda: 'Direct' not in captions(), 'closed direct-launch window')
            launch(other_unit + '-rename', f'{root}/identity/Open', 'Open')
            snapshot('open-root-populated', icon_ink)
            focus('Final')
            go(f'{root}/identity', 'identity')
            # Direct, existing and Open are the three visible icon cells, in name order.
            snapshot('rename-source', lambda image: ink(image.crop((666, 225, 762, 326))))
            click(point(x + 455, y + 150))
            key('KEY_F2')
            wait_for(lambda: kwin_query('emit(workspace.activeWindow.caption);') == [['Rename Item']],
                     'F2 opened the active Rename Item editor')
            snapshot('rename-editor')
            key('KEY_LEFTCTRL', 'KEY_A')
            vmctl.type_text(VM, 'Renamed')
            snapshot('rename-edited')
            key('KEY_ENTER')
            wait_for(lambda: guest_file(f'{root}/identity/Renamed/Sample.txt'),
                     'second Explorer renamed the displayed root')
            wait_for(lambda: 'Renamed' in captions(), 'open root received the KIO rename redirect')
            focus('Renamed')
            snapshot('renamed-root-kept-row', icon_ink)
            key('KEY_LEFTCTRL', 'KEY_E')
            vmctl.type_text(VM, 'not-a-match')
            empty('renamed-root-filtered-empty', 'icons')
        finally:
            try:
                stop_unit(other_unit + '-rename')
            finally:
                stop_unit(other_unit)

    try:
        launch(unit, f'{root}/Classic-demo', 'Classic-demo')
        snapshot('parent-populated', icon_ink)
        click(point(x + 220, y + 150))
        key('KEY_ENTER')
        wait_for(lambda: 'Documents' in captions(), 'opened empty Documents from the icon view')
        empty('initial-icons', 'icons')
        view('details')
        empty('icons-to-details', 'details')
        resize(-120, -40)
        empty('narrow-details', 'details')
        view('icons')
        empty('details-to-icons', 'icons')
        resize(120, 40)
        empty('wider-icons', 'icons')
        view('details')
        empty('back-to-details', 'details')
        # Keep the test file's contents and inode through live model changes; never touch user data.
        user(f'printf "fixture\\n" > {root}/Sample.txt; mv {root}/Sample.txt {root}/Classic-demo/Documents/')
        rows = populated('populated-in-place')
        key('KEY_LEFTCTRL', 'KEY_E')
        vmctl.type_text(VM, 'not-a-match')
        empty('filtered-empty', 'details')
        key('KEY_LEFTCTRL', 'KEY_A')
        key('KEY_BACKSPACE')
        assert rows == populated('filter-cleared'), 'filter changed populated Details geometry'
        user(f'mv {root}/Classic-demo/Documents/Sample.txt {root}/')
        empty('last-file-removed', 'details')
        key('KEY_LEFTALT', 'KEY_LEFT')
        wait_for(lambda: 'Classic-demo' in captions(), 'Back to populated icon view')
        key('KEY_LEFTALT', 'KEY_RIGHT')
        wait_for(lambda: 'Documents' in captions(), 'Forward reopens saved empty Details view')
        empty('forward-to-details', 'details')
        view('list')
        empty('empty-list', 'list')
        resize(-120, -40)
        click(empty('narrow-list', 'list'), 'right')
        shot(out / 'label-background-menu.png')
        # Only the background menu has a View submenu; use it to apply Details.
        key('KEY_V')
        key('KEY_UP')
        key('KEY_ENTER')
        empty('label-menu-to-details', 'details')
        if scale == 1:
            resize(120, 40)
            webdav()
            root_identity()
    finally:
        stop_unit(unit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true', help='use the development Explorer already installed in the lab')
    parser.add_argument('--scales', nargs='+', type=float, choices=(1, 1.5), default=(1, 1.5))
    args = parser.parse_args()
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    initial_mode = user('~/.local/bin/win7-classic status')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    root = user('mktemp -d /tmp/w7-empty.XXXXXXXX')
    try:
        toggle('current')
        toggle('windows')
        toggle('current')
        toggle('windows')
        for scale in args.scales:
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}')
            exercise(args.out / f'scale-{scale:g}', scale, root)
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}; rm -r {root}')
        toggle(initial_mode)
    print('PASS: empty view changes, resizing, live file changes, filters and history; listing and root identity at 100%')


if __name__ == '__main__':
    main()
