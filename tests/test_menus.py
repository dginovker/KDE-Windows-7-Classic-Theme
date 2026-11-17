#!/usr/bin/env python3
"""Native Organize popup pixels through the installed system Qt style (#18)."""
import json
from pathlib import Path
import sys
import time
from PIL import Image, ImageChops
from lab import ROOT, VM, vmctl, install, toggle, user, shot, kwin_script, wait_for, windows, activate, kwin_query

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-menus-test')
FACE, WHITE, GRAY, BLUE = (212, 208, 200), (255, 255, 255), (128, 128, 128), (10, 36, 106)


def popup_box(image):
    # Locate the real compositor surface, rather than trusting Wayland's synthetic global popup coordinates.
    for y in range(450, 550):
        xs = [x for x in range(255, 450) if image.getpixel((x, y)) == (64, 64, 64)]
        if len(xs) == 168 and xs[-1] - xs[0] == 167:
            return (xs[0], y - 267, xs[-1] + 1, y + 1)
    raise AssertionError('no 168x268 menu bevel in lab screenshot')


def popup_bevel(image):
    pixels = image.load()
    for bottom in range(150, 756):
        left = None
        for x in range(250, 1281):
            if x < 1280 and pixels[x, bottom] == (64, 64, 64):
                if left is None:
                    left = x
                continue
            if left is not None:
                right = x - 1
                if 60 < right - left < 600 and all(pixels[col, bottom - 1] == GRAY for col in range(left + 1, right)):
                    for top in range(max(145, bottom - 500), bottom - 30):
                        if (all(pixels[col, top + 1] == WHITE for col in range(left + 1, right - 1))
                                and all(pixels[left + 1, row] == WHITE and pixels[right, row] == (64, 64, 64)
                                        for row in range(top + 1, bottom - 1))):
                            return (left, top, right + 1, bottom + 1)
                left = None
    return None


def assert_live_popup(name):
    path = OUT / f'{name}-menu.png'
    def visible():
        shot(path)
        return popup_bevel(Image.open(path).convert('RGB'))
    wait_for(visible, f'{name} native popup bevel', timeout=8)
    box = popup_bevel(Image.open(path).convert('RGB'))
    x, y = box[0] + 30, box[3] - 12
    vmctl.pointer(VM, x, y)
    vmctl.pointer(VM, x + 1, y)
    time.sleep(0.4)
    shot(OUT / f'{name}-selected.png')
    image = Image.open(OUT / f'{name}-selected.png').convert('RGB')
    assert image.getpixel((box[2] - 14, y)) == BLUE, f'{name}: popup row did not select'
    (OUT / f'{name}-popup.json').write_text(json.dumps({'box': box, 'selectedY': y}))
    return box


def assert_disabled_shortcut(image):
    pixels = image.load()
    ink = [(x, y) for y in range(image.height - 1) for x in range(image.width - 1) if pixels[x, y] == GRAY]
    assert ink, 'disabled shortcut has no GrayText ink'
    exposed = [(x + 1, y + 1) for x, y in ink if pixels[x + 1, y + 1] != GRAY]
    assert exposed and all(pixels[x, y] == WHITE for x, y in exposed), 'disabled shortcut has no offset white emboss'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    toggle('windows')
    vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_menus.py'), '/tmp/fixture_menus.py')
    vmctl.run(VM, 'chmod 644 /tmp/fixture_menus.py', 10)
    user('rm -f /tmp/fixture-menu.json /tmp/fixture-menu-triggered /tmp/fixture-submenu.png /tmp/fixture-submenu.json /tmp/fixture-view.png; '
         'systemd-run --user --collect -q python3 /tmp/fixture_menus.py')
    wait_for(lambda: 'python3' in windows(), 'menu fixture')
    kwin_script('for (const w of workspace.windowList()) if(w.caption=="Classic menu fixture") '
                '{ w.frameGeometry={x:256,y:120,width:768,height:560}; workspace.activeWindow=w; }')
    vmctl.pointer(VM, 293, 194, 'left')
    vmctl.pointer(VM, 100, 400)
    wait_for(lambda: user('test -f /tmp/fixture-menu.json && echo yes', check=False) == 'yes', 'menu metrics')
    metrics = json.loads(user('cat /tmp/fixture-menu.json'))
    (OUT / 'menu.json').write_text(json.dumps(metrics, indent=2))
    assert metrics['style'].lower() == 'win7classic'
    assert metrics['size'] == [168, 268], metrics
    shot(OUT / 'organize.png')
    image = Image.open(OUT / 'organize.png').convert('RGB')
    box = popup_box(image)
    ours = image.crop(box)
    native = Image.open(ROOT / 'reference/screenshots/w7-explorer-organize.png').convert('RGB').crop((263, 207, 431, 475))
    diff = ImageChops.difference(ours, native)
    # Only glyph ink/art is masked; frame, column padding, every separator and submenu arrow stay asserted.
    masks = [(35, 0, 55, 10)]  # native mouse pointer
    for label, (_, y, _, h) in metrics['actions'].items():
        assert h == (18 if label in ('Cut', 'Copy', 'Paste', 'Layout', 'Delete') else 17), (label, h)
        masks.append((21, y + 2, 149, y + 16))
        if h == 18:
            masks.append((4, y, 21, y + h))
    for mask in masks:
        diff.paste((0, 0, 0), mask)
    ours.save(OUT / 'organize-ours.png')
    native.save(OUT / 'organize-native.png')
    diff.point(lambda v: 255 if v else 0).save(OUT / 'organize-diff.png')
    assert diff.getbbox() is None, f'Organize structural mismatch: {diff.getbbox()}'
    # The disabled labels have GrayText ink plus a white emboss, never a dimmed selection color.
    disabled = list(ours.crop((22, 190, 149, 221)).get_flattened_data())
    assert any(max(c) < 190 for c in disabled) and any(min(c) > 225 for c in disabled), 'missing disabled text emboss'
    print('native menu frame, 17/18px rows, padding, separators and 4x7 submenu arrow match')

    x, y = box[:2]
    vmctl.pointer(VM, x + 60, y + 108)
    vmctl.pointer(VM, x + 61, y + 108)
    time.sleep(0.5)
    shot(OUT / 'hover.png')
    hover = Image.open(OUT / 'hover.png').convert('RGB').crop(box)
    assert hover.getpixel((150, 108)) == BLUE, 'selected row is not COLOR_HIGHLIGHT'
    assert any(min(c) > 225 for c in hover.crop((22, 102, 80, 115)).get_flattened_data()), 'selected text is not COLOR_HIGHLIGHTTEXT'
    vmctl.pointer(VM, x + 60, y + 133)
    vmctl.pointer(VM, x + 61, y + 133)
    wait_for(lambda: user('test -f /tmp/fixture-submenu.png && echo yes', check=False) == 'yes', 'submenu')
    shot(OUT / 'submenu.png')
    vmctl.transfer(VM, 'get', str(OUT / 'submenu-widget.png'), '/tmp/fixture-submenu.png')
    sub = Image.open(OUT / 'submenu-widget.png').convert('RGB')
    # Also cover the shortcut-bearing submenu, which is not present in the native shell capture.
    radio = sub.crop((3, 3, 18, 20))
    tick = sub.crop((3, 37, 18, 54))
    assert sum(c == (0, 0, 0) for c in radio.get_flattened_data()) == 32, 'native menu bullet is not a 6px raster'
    assert sum(c == (0, 0, 0) for c in tick.get_flattened_data()) == 21, 'DFC_MENU check is not a 7px raster'
    assert radio.tobytes() != tick.tobytes(), 'exclusive and checked actions use the same mark'
    shortcut_box = json.loads(user('cat /tmp/fixture-submenu.json'))['shortcutBox']
    shortcut = sub.crop(shortcut_box)
    shortcut.save(OUT / 'disabled-shortcut.png')
    assert_disabled_shortcut(shortcut)
    no_emboss = shortcut.copy()
    no_emboss.putdata([FACE if color == WHITE else color for color in shortcut.get_flattened_data()])
    no_emboss.save(OUT / 'disabled-shortcut-no-emboss.png')
    try:
        assert_disabled_shortcut(no_emboss)
    except AssertionError:
        print('negative control: removing the disabled shortcut emboss is detected')
    else:
        raise AssertionError('disabled shortcut assertion accepted missing emboss')
    vmctl.keys(VM, 'KEY_ESC')
    vmctl.pointer(VM, x + 55, y + 256, 'left')
    wait_for(lambda: user('cat /tmp/fixture-menu-triggered 2>/dev/null', check=False) == 'Close', 'menu action triggered')
    print('hover colors, distinct check/radio rasters, disabled shortcut and action interaction passed')

    vmctl.pointer(VM, 380, 194, 'left')
    vmctl.pointer(VM, 100, 400)
    wait_for(lambda: user('test -f /tmp/fixture-view.png && echo yes', check=False) == 'yes', 'View submenu raster')
    native_view = Image.open(ROOT / 'reference/screenshots/w7-desktop-view-submenu.png').convert('RGB').crop((259, 420, 412, 563))
    native_hover = Image.open(ROOT / 'reference/screenshots/w7-desktop-view-checked-hover.png').convert('RGB').crop((259, 420, 412, 563))
    for name, reference, downs in [('view', native_view, 0), ('view-check-hover', native_hover, 5)]:
        for _ in range(downs):
            vmctl.keys(VM, 'KEY_DOWN')
        time.sleep(0.5)
        vmctl.transfer(VM, 'get', str(OUT / f'{name}-ours.png'), '/tmp/fixture-view.png')
        raster = Image.open(OUT / f'{name}-ours.png').convert('RGB')
        assert raster.size == reference.size, (raster.size, reference.size)
        difference = ImageChops.difference(raster, reference)
        for top in (3, 20, 37, 63, 80, 106, 123):
            difference.paste((0, 0, 0), (18, top + 2, 150, top + 16))
        if downs:
            difference.paste((0, 0, 0), (136, 89, 153, 113))  # genuine hover pointer crosses the right bevel
        reference.save(OUT / f'{name}-native.png')
        difference.point(lambda v: 255 if v else 0).save(OUT / f'{name}-diff.png')
        assert difference.getbbox() is None, (name, difference.getbbox())
    for _ in range(3):
        vmctl.keys(VM, 'KEY_UP')
    time.sleep(0.5)
    vmctl.transfer(VM, 'get', str(OUT / 'view-radio-hover-ours.png'), '/tmp/fixture-view.png')
    radio_hover = Image.open(OUT / 'view-radio-hover-ours.png').convert('RGB').crop((3, 20, 18, 37))
    native_radio = Image.open(ROOT / 'reference/screenshots/w7-explorer-view-radio-hover.png').convert('RGB').crop((1002, 439, 1017, 456))
    native_radio.save(OUT / 'view-radio-hover-native.png')
    assert ImageChops.difference(radio_hover, native_radio).getbbox() is None, 'selected native radio mismatch'
    vmctl.keys(VM, 'KEY_ESC')
    print('native View submenu: radio, checks, selected check, frame and row colors match genuine captures')

    user('pkill -f "^/usr/bin/python3 /tmp/fixture_menus.py"; true')
    for resource, command in [('org.win7classic.explorer', '~/.local/bin/win7-explorer'),
                              ('org.kde.dolphin', 'dolphin'), ('org.kde.kate', 'kate')]:
        user(f'systemd-run --user --collect -q {command}')
        wait_for(lambda: resource in windows(), resource)
        activate(resource)
        kwin_script(f'for(const w of workspace.windowList()) if(w.resourceClass=="{resource}") '
                    '{w.frameGeometry={x:256,y:120,width:768,height:560};}')
        if resource == 'org.win7classic.explorer':
            vmctl.pointer(VM, 293, 194, 'left')
        elif resource == 'org.kde.dolphin':
            if '--suppress-dolphin-popup' not in sys.argv:
                vmctl.pointer(VM, 850, 550, 'right')
        else:
            vmctl.keys(VM, 'KEY_LEFTALT', 'KEY_F')
        vmctl.pointer(VM, 100, 400)
        assert_live_popup(resource)
        if resource == 'org.kde.dolphin':
            vmctl.keys(VM, 'KEY_END')
            vmctl.keys(VM, 'KEY_ENTER')
            wait_for(lambda: any('Properties' in row[0] for row in kwin_query(
                'for(const w of workspace.windowList()) emit(w.caption);')), 'Dolphin Properties action')
            shot(OUT / 'dolphin-properties.png')
            vmctl.keys(VM, 'KEY_ESC')
        else:
            vmctl.keys(VM, 'KEY_ESC')
    vmctl.pointer(VM, 1100, 650, 'right')
    vmctl.pointer(VM, 100, 400)
    assert_live_popup('plasma-desktop')
    vmctl.keys(VM, 'KEY_ESC')
    toggle('current')
    print('ALL MENU CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
