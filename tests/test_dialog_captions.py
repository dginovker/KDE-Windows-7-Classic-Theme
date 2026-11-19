#!/usr/bin/env python3
"""Compare real modal Classic captions and exercise Explorer's pending edits (#57)."""
import argparse
import json
from pathlib import Path
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, digest, install, kwin_query, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, exists, key

PROPERTIES = 'Properties for Documents'
OPTIONS = 'Folder Options'
MAIN = 'Caption-demo'
REF = ROOT / 'reference/screenshots'
OPTIONSRC = '~/.config/win7-explorer-optionsrc'


def frame(title):
    rows = kwin_query(f'for (const w of workspace.windowList()) if (w.caption === {json.dumps(title)}) '
                      'emit(w.modal, w.frameGeometry.x, w.frameGeometry.y, w.width, w.height, '
                      'w.clientGeometry.x, w.clientGeometry.y, w.minimized, w.maximizeMode);')
    assert len(rows) <= 1, rows
    return rows[0] if rows else None


def close_only(image, native, scale):
    """50×14 logical strip ending at the Close edge; no label or frame-width assumptions."""
    assert image.size == (round(50 * scale), round(14 * scale)), image.size
    assert native.size == (50, 14), native.size
    split = round(34 * scale)
    # A blue caption column above/below an unexpected button is not enough: check the whole strip.
    # Ignore one transitioning pixel beside Close at a fractional buffer phase.
    preceding = image.crop((0, 0, split - int(scale != 1), image.height))
    for r, g, b in preceding.getdata():
        assert b > g + 12 and g > r + 12, f'unexpected bevel/glyph in the space before Close: {(r, g, b)}'
    button = image.crop((split, 0, image.width, image.height))
    target = native.crop((34, 0, 50, 14))
    if scale == 1:
        assert ImageChops.difference(button, target).getbbox() is None, 'Close glyph/bevel/position differs from Windows 7'
    else:
        # Sample glyph and bevel interiors, not fractionally filtered edges. Footprint uses physical pixels.
        sw, sh = button.size
        assert (sw, sh) == (24, 21), (sw, sh)
        assert all(max(button.getpixel(pt)) <= 48 for pt in ((11, 9), (12, 9), (11, 10), (12, 10))), 'Close glyph missing'
        assert min(button.getpixel((sw // 2, 0))) > 212, 'raised top edge missing'
        assert max(button.getpixel((sw // 2, sh - 1))) < 110, 'bottom edge missing or button not 14 logical px high'


def crop_screen(out, tag, x, y, w, h, scale):
    sw, sh = vmctl.screen_size(VM)
    vmctl.pointer(VM, sw - 8, sh - 80)
    time.sleep(.35)
    shot(out / f'{tag}-desktop.png')
    # Anchor width/height to the sampled physical origin to avoid a half-pixel rounding difference.
    x, y = round(x * scale), round(y * scale)
    with Image.open(out / f'{tag}-desktop.png') as image:
        crop = image.convert('RGB').crop((x, y, x + round(w * scale), y + round(h * scale)))
    crop.save(out / f'{tag}.png')
    return crop


def caption(out, tag, state, scale, strip_width=50):
    _, x, y, w, *_ = state
    return crop_screen(out, tag, float(x) + float(w) - 6 - strip_width, float(y) + 6, strip_width, 14, scale)


def point(x, y, scale):
    return round(x * scale), round(y * scale)


def exercise(out, scale, root, message_oracle):
    out.mkdir(parents=True, exist_ok=True)
    path = f'{root}/{scale:g}/{MAIN}'
    unit = f'{Path(root).name}-{round(scale * 100)}'
    user(f'mkdir -p {path}/Documents; systemd-run --user --collect -q --unit={unit} ~/.local/bin/win7-explorer {path}')
    wait_for(lambda: MAIN in captions(), MAIN)
    kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass === "{EXPLORER}" && w.caption === "{MAIN}") '
                '{ w.frameGeometry = {x: 42, y: 34, width: 730, height: 405}; workspace.activeWindow = w; }')

    def open_dialog(title):
        _, _, _, _, _, cx, cy, *_ = frame(MAIN)
        cx, cy = float(cx), float(cy)
        if title == PROPERTIES:
            click(point(cx + 214, cy + 123, scale))
            key('KEY_LEFTALT', 'KEY_ENTER')
        else:
            click(point(cx + 40, cy + 51, scale))
            key('KEY_F')  # Organize → Folder and search options
        wait_for(lambda: title in captions(), title)
        state = frame(title)
        assert state[0] == 'true', (title, state)
        return state

    current = digest(), user('sha256sum ~/.config/kwinrc ~/.config/kdeglobals')
    # Use the *same open modal* before and after switching, not a newly opened surrogate dialog.
    open_dialog(OPTIONS)

    def stock_caption(tag):
        _, x, y, w, _, _, cy, *_ = frame(OPTIONS)
        height = float(cy) - float(y)
        assert height > 14, height
        return crop_screen(out, tag, float(x) + float(w) - 72, float(y), 72, height, scale)

    before = stock_caption('current-before')
    toggle('windows')
    close_only(caption(out, 'options-live-classic', frame(OPTIONS), scale),
               Image.open(REF / 'w7-folder-options-caption.png').convert('RGB'), scale)
    toggle('current')
    assert ImageChops.difference(before, stock_caption('current-return')).getbbox() is None, 'current-mode caption changed'
    assert current == (digest(), user('sha256sum ~/.config/kwinrc ~/.config/kdeglobals')), 'current profile/config changed'
    key('KEY_ESC')
    toggle('windows')
    classic_kwin = user('sha256sum ~/.config/kwinrc')

    for title, name in [(PROPERTIES, 'folder-properties'), (OPTIONS, 'folder-options')]:
        native = Image.open(REF / f'w7-{name}-caption.png').convert('RGB')
        for way in ('Close', 'Escape', 'OK'):
            _, x, y, w, h, *_ = state = open_dialog(title)
            x, y, w, h = map(float, (x, y, w, h))
            if way == 'Close':
                close_only(caption(out, name, state, scale), native, scale)
            if title == PROPERTIES:
                click(point(x + 150, y + 73, scale))
                key('KEY_LEFTCTRL', 'KEY_A')
                vmctl.type_text(VM, 'Saved')
                assert exists(f'{path}/Documents') and not exists(f'{path}/Saved'), 'KIO edit was not pending'
            else:
                assert not exists(OPTIONSRC), 'options written before this edit'
                key('KEY_LEFTALT', 'KEY_H')
                assert not exists(OPTIONSRC), 'options written before acceptance'
            if way == 'Close':
                click(point(x + w - 14, y + 12, scale))
            elif way == 'Escape':
                key('KEY_ESC')
            elif title == PROPERTIES:
                click(point(x + w - 130, y + h - 23, scale))  # KDE's original footer OK
            else:
                key('KEY_ENTER')
            wait_for(lambda: title not in captions(), f'{title} dismissed by {way}')
            if title == PROPERTIES:
                assert exists(f'{path}/Saved') == (way == 'OK') and exists(f'{path}/Documents') == (way != 'OK'), way
            else:
                assert exists(OPTIONSRC) == (way == 'OK'), way
                if way == 'OK':
                    assert user(f'kreadconfig6 --file win7-explorer-optionsrc --group View --key ShowHidden') == 'true'

    def window_button(offset):
        _, x, y, w, *_, maximized = frame(MAIN)
        click(point(float(x) + float(w) - offset, float(y) + (8 if maximized == '3' else 12), scale))

    native_main = Image.open(REF / 'w7-taskbar.png').convert('RGB').crop((968, 126, 1018, 140))
    actual = caption(out, 'ordinary-explorer', frame(MAIN), scale)
    if scale == 1:
        assert ImageChops.difference(native_main, actual).getbbox() is None, 'ordinary window buttons changed'
    # Actual pointer clicks, including the restore glyph on the maximized frame.
    window_button(30)
    wait_for(lambda: frame(MAIN)[-1] == '3', 'Explorer maximized')
    window_button(26)
    wait_for(lambda: frame(MAIN)[-1] == '0', 'Explorer restored')
    window_button(47)
    wait_for(lambda: frame(MAIN)[-2] == 'true', 'Explorer minimized')
    kwin_script(f'for (const w of workspace.windowList()) if (w.caption === "{MAIN}") '
                '{ w.minimized = false; workspace.activeWindow = w; }')
    window_button(14)
    wait_for(lambda: frame(MAIN) is None, 'normal Explorer caption Close')
    assert user('sha256sum ~/.config/kwinrc') == classic_kwin, 'Classic window config changed'

    for kind, backend in [('nonmodal', 'wayland'), ('message', 'wayland'), ('help', 'xcb')]:
        title = 'Modal caption probe' if kind == 'message' else f'{kind} caption probe'
        probe = f'{unit}-{kind}'
        receipt = f'{root}/{probe}-clicked'
        user(f'systemd-run --user --collect -q --unit={probe} --setenv=QT_QPA_PLATFORM={backend} '
             f'/usr/bin/python3 {root}/fixture_dialog_caption.py {kind} {receipt}')
        try:
            wait_for(lambda: frame(title) is not None, title)
            state = frame(title)
            assert (state[0] == 'true') == (kind != 'nonmodal'), state
            result = caption(out, kind, state, scale)
            if kind == 'message':
                close_only(result, message_oracle, scale)
            elif kind == 'nonmodal' and scale == 1:
                assert ImageChops.difference(native_main, result).getbbox() is None, 'nonmodal buttons changed'
            elif kind == 'help':
                _, x, y, w, h, *_ = state
                click(point(float(x) + float(w) - 32, float(y) + 12, scale))
                wait_for(lambda: exists(receipt), 'KWin to enter the client’s real What’s This mode')
                click(point(float(x) + float(w) / 2, float(y) + float(h) / 2, scale))
                time.sleep(.45)
                shot(out / 'context-help-after-click.png')  # verify the real Qt What's This bubble
        finally:
            user(f'systemctl --user stop {probe}', check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--message-oracle', type=Path, required=True, help='genuine 50x14 Windows 7 modal caption crop')
    parser.add_argument('--installed', action='store_true', help='test the installed candidate without reinstalling')
    args = parser.parse_args()
    message = Image.open(args.message_oracle).convert('RGB')
    close_only(message, Image.open(REF / 'w7-folder-options-caption.png').convert('RGB'), 1)
    vmctl.start(VM)
    if not args.installed:
        install(reset=False)
    original = user('~/.local/bin/win7-classic status')
    output, = json.loads(user('kscreen-doctor -j'))['outputs']
    root = user('mktemp -d /tmp/w7captions.XXXXXXXX')
    vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_dialog_caption.py'), f'{root}/fixture_dialog_caption.py')
    vmctl.run(VM, f'chmod 644 {root}/fixture_dialog_caption.py', 10)
    user(f'if test -e {OPTIONSRC}; then mv {OPTIONSRC} {root}/original-options; fi')
    try:
        for scale in (1, 1.5):
            user(f'kscreen-doctor output.{output["name"]}.scale.{scale}')
            toggle('current')
            try:
                exercise(args.out / f'{scale:g}x', scale, root, message)
            finally:
                user(f'systemctl --user stop {Path(root).name}-{round(scale * 100)} 2>/dev/null || true; rm -f {OPTIONSRC}')
    finally:
        user(f'kscreen-doctor output.{output["name"]}.scale.{output["scale"]}; '
             f'if test -e {root}/original-options; then mv {root}/original-options {OPTIONSRC}; fi; rm -r {root}')
        toggle(original)
    print('PASS: modal captions, real Explorer Close/Escape/OK, normal/nonmodal and current-mode negatives')


if __name__ == '__main__':
    main()
