#!/usr/bin/env python3
"""Drive KDE's folder Properties from Explorer without changing any real files (#38)."""
import argparse
import csv
from functools import partial
import io
import json
from pathlib import Path
import shlex
import subprocess
import time

from PIL import Image, ImageOps

from lab import ROOT, VM, executable, install, kwin_query, shot, toggle, user, vmctl, wait_for
from test_explorer import captions, click, key


def check_general(image, scale, native=False):
    # Compare chrome, not labels (KDE has additional data/widgets in the same groups).
    width, height = (n / scale for n in image.size)
    assert 360 <= width <= 415 and 460 <= height <= 525, (width, height)
    left = round((17 if native else 15) * scale)
    bands = []
    center = image.width // 2
    for y in range(round(84 * scale), image.height - round(48 * scale)):
        if all(image.getpixel((x, y)) == (128, 128, 128) for x in (left + round(20 * scale), center, image.width - round(32 * scale))):
            if not bands or y > bands[-1][-1] + 1:
                bands.append([])
            bands[-1].append(y)
    assert len(bands) == 3, (scale, bands)
    assert 92 <= bands[0][0] / scale <= 108, (scale, bands)
    page_bottom = next((y for y in range(image.height - round(44 * scale), image.height - round(34 * scale))
                        if image.getpixel((center, y)) == (64, 64, 64)), None)
    assert page_bottom is not None, 'missing page surround'
    assert any(image.getpixel((image.width - round(14 * scale), y)) == (255, 255, 255)
               for y in range(round(46 * scale), round(51 * scale))), 'page top too close to the caption or missing'
    # A real folder glyph on an unframed face, not a permanently raised icon button.
    face = (212, 208, 200)
    assert all(image.getpixel((x, y)) == face for x in range(round(24 * scale), round(30 * scale))
               for y in range(round(56 * scale), round(60 * scale))), 'raised idle icon surround'
    icon = image.crop((round(25 * scale), round(61 * scale), round(61 * scale), round(96 * scale)))
    assert sum(r > 225 and g > 190 and b < 190 for r, g, b in icon.getdata()) >= 80 * scale**2, 'missing folder art'
    # Use the bottom bevels (independent of translated button labels and focus text).
    for y in range(image.height - round(16 * scale), image.height - round(8 * scale)):
        runs = horizontal_runs(image, y, {(0, 0, 0), (64, 64, 64)})
        buttons = [(a, b) for a, b in runs if 72 <= (b - a) / scale <= 80]
        if len(buttons) == (3 if native else 2):
            break
    else:
        raise AssertionError('missing compact button bevels')
    assert all(4 <= (b[0] - a[1]) / scale <= 8 for a, b in zip(buttons, buttons[1:])), buttons
    assert 7 <= (image.width - buttons[-1][1]) / scale <= 11, ('footer does not align to page edge', buttons)
    print(f'{scale:g}x {"Windows 7" if native else "Explorer"}: {width:g}×{height:g} logical; three etched groups, flat icon, '
          f'button bevels at {buttons}', flush=True)


def horizontal_runs(image, y, colors):
    runs = []
    for x in range(image.width):
        if image.getpixel((x, y)) in colors:
            if runs and runs[-1][1] == x:
                runs[-1] = runs[-1][0], x + 1
            else:
                runs.append((x, x + 1))
    return runs


def active_frame():
    rows = kwin_query('for (const w of workspace.windowList()) if (workspace.activeWindow === w) '
                      'emit(w.caption, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height);')
    assert len(rows) == 1, rows
    return rows[0][0], tuple(map(float, rows[0][1:]))


def observe_frame(scale, tag, *, fresh):
    row, = kwin_query('const w = workspace.activeWindow; const f = w.frameGeometry; '
                      'const a = workspace.clientArea(KWin.WorkArea, w); '
                      'emit(w.caption, w.internalId, w.pid, f.x-a.x, f.y-a.y, a.x+a.width-f.x-f.width, a.y+a.height-f.y-f.height);')
    title, ident, pid, *slack = row
    assert title == 'Properties for Documents', row
    if fresh:
        assert min(map(float, slack)) * scale >= -0.5 - 1e-6, (tag, 'frame exceeds work area', row)
    print(f'{scale:g}x {tag} {ident}: frame slack L/T/R/B={slack}, pid={pid}', flush=True)
    return ident, pid


def ocr(image, path, psm, tsv=False):
    image = image.resize((image.width * 4, image.height * 4), Image.Resampling.LANCZOS)
    image.save(path)
    return subprocess.check_output(['tesseract', str(path), 'stdout', '--psm', psm] + (['tsv'] if tsv else []),
                                   stderr=subprocess.DEVNULL, text=True).strip()


def name_box(image, scale):
    # The editable name is the first wide field below the tabs. Isolate its interior from labels.
    bands = []
    for y in range(round(58 * scale), round(155 * scale)):
        # Focus can scroll the page horizontally, moving the field to the viewport edge.
        runs = []
        for x in range(image.width - round(12 * scale)):
            if image.getpixel((x, y)) == (255, 255, 255):
                if not runs or x - runs[-1][-1] > round(50 * scale):
                    runs.append([])
                runs[-1].append(x)
        xs = max(runs, key=len, default=[])
        if len(xs) >= round(120 * scale) and xs[-1] - xs[0] - len(xs) < round(100 * scale):
            if not bands or y > bands[-1][-1][0] + 2:
                bands.append([])
            bands[-1].append((y, xs[0], xs[-1]))
    eligible = [b for b in bands if 11 <= (b[-1][0] - b[0][0] + 1) / scale <= 50]
    assert eligible, bands
    band = max(eligible, key=lambda b: sum(right - left for _, left, right in b))
    return min(r[1] for r in band) + round(2 * scale), band[0][0], max(r[2] for r in band) - round(3 * scale), band[-1][0] + 1


def check_name(image, scale, path, name):
    box = name_box(image, scale)
    # Exclude any scroll-area edge from OCR, without dropping any characters.
    x0, y0, x1, y1 = box
    crop = image.crop((x0, y0, x1 - round(10 * scale), y1)).convert('L').point(lambda v: 0 if v < 160 else 255)
    parsed = ocr(ImageOps.expand(crop, border=5, fill=255), path, '7')
    assert parsed == name, (path, parsed, name)
    print(f'{scale:g}x {path.stem}: {parsed!r} in the name field', flush=True)


def words(image, path, y=0, psm='11'):
    tsv = ocr(image, path, psm, tsv=True)
    return {r['text'].strip(' |[]\\:‘’()'): ((int(r['left']) + int(r['width']) / 2) / 4,
                                           (int(r['top']) + int(r['height']) / 2) / 4 + y)
            for r in csv.DictReader(io.StringIO(tsv), delimiter='\t', quoting=csv.QUOTE_NONE) if r['text']}


def exercise(out, scale, output, stationary=False, fresh_tight=False, resize=False, *, packaged=False):
    switch = partial(toggle, packaged=packaged)
    out.mkdir(parents=True, exist_ok=True)
    root = user('mktemp -d /tmp/w7prop.XXXXXXXX')
    unit = Path(root).name
    folder = f'{root}/Classic-demo'
    try:
        user(f'mkdir -p {folder}/Documents; chmod 755 {folder}/Documents; '
             f"systemd-run --user --collect -q --unit={unit} {executable('win7-explorer', packaged)} {folder}")
        wait_for(lambda: 'Classic-demo' in captions(), 'Explorer fixture')
        wait_for(lambda: active_frame()[0] == 'Classic-demo', 'active Explorer fixture')

        def open_properties():
            key('KEY_LEFTCTRL', 'KEY_A')  # Exactly one item; avoid positioning the parent or the modal.
            key('KEY_LEFTALT', 'KEY_ENTER')
            wait_for(lambda: active_frame()[0] == 'Properties for Documents', 'folder Properties')
            return active_frame()[1]

        def capture(tag):
            sw, sh = vmctl.screen_size(VM)
            vmctl.pointer(VM, sw - 7, sh // 2)
            time.sleep(.35)
            path = out / f'{tag}-desktop.png'
            shot(path)
            title, (x, y, w, h) = active_frame()
            assert title == 'Properties for Documents', title
            image = Image.open(path).convert('RGB').crop(tuple(round(n * scale) for n in (x, y, x+w, y+h)))
            image.save(out / f'{tag}.png')
            return image

        def at(x, y):
            click((round((frame[0]+x) * scale), round((frame[1]+y) * scale)))

        def edit(name, image):
            x, y, w, h = name_box(image, scale)
            at((x+w)/(2*scale), (y+h)/(2*scale))
            key('KEY_LEFTCTRL', 'KEY_A')
            vmctl.type_text(VM, name)
            key("KEY_TAB")  # Remove the blinking caret before reading the field.

        def state():
            return user(f'find {folder} -mindepth 1 -printf "%P %m\\n"')

        frame = open_properties()
        ident = observe_frame(scale, 'fresh', fresh=True)
        general = capture('general')
        if resize:
            x, y, w, h = frame
            vmctl.pointer(VM, round((x + w - 12) * scale), round((y + h - 12) * scale))

            def meta(down):
                event = {'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': 'meta_l'}}}
                vmctl.virsh('qemu-monitor-command', VM, json.dumps({
                    'execute': 'input-send-event', 'arguments': {'events': [event]}}))

            # KWin's stock Meta+right drag applies the real client resize constraints.
            meta(True)
            try:
                vmctl.button(VM, 'right', True)
                try:
                    vmctl.pointer(VM, round((x + 12) * scale), round((y + 12) * scale))
                finally:
                    vmctl.button(VM, 'right', False)
            finally:
                meta(False)
            title, frame = active_frame()
            assert title == 'Properties for Documents' and observe_frame(scale, 'minimum', fresh=True) == ident
            row, = kwin_query('const w = workspace.activeWindow; '
                              'emit(w.clientGeometry.width, w.clientGeometry.height, w.minSize.width, w.minSize.height);')
            cw, ch, mw, mh = map(float, row)
            assert all(abs(a-b) * scale <= 1 for a, b in ((cw, mw), (ch, mh))), ('did not reach minimum', row)
            assert frame[2] < w and frame[3] < h, (frame, w, h)
            print(f'{scale:g}x user drag: {w:g}×{h:g} → {frame[2]:g}×{frame[3]:g}, client {cw:g}×{ch:g}, '
                  f'advertised minimum {mw:g}×{mh:g}', flush=True)
            before = capture('minimum')
            # Drag the page's vertical scrollbar without touching the footer.
            x = round((frame[0] + frame[2] - 17) * scale)
            vmctl.pointer(VM, x, round((frame[1] + 53) * scale))
            vmctl.button(VM, 'left', True)
            try:
                vmctl.pointer(VM, x, round((frame[1] + frame[3] - 68) * scale))
            finally:
                vmctl.button(VM, 'left', False)
            after = capture('minimum-scrolled')
            page = after.crop(tuple(round(v * scale) for v in (15, 48, 106, frame[3] - 46)))
            assert 'Free space' in ocr(page, out / 'minimum-storage.png', '6'), 'storage group unreachable at minimum size'
            for tag, image in (('before', before), ('after', after)):
                for label, center, width in (('OK', 46, 32), ('Cancel', frame[2] - 46, 45)):
                    bounds = (center - width/2, frame[3] - 31, center + width/2, frame[3] - 19)
                    crop = image.crop(tuple(round(v * scale) for v in bounds))
                    ink = crop.convert('L').point(lambda v: 0 if v < 140 else 255)
                    text = ocr(ImageOps.expand(ink, border=4, fill=255), out / f'minimum-{tag}-{label}.png', '7')
                    assert text.casefold() == label.casefold(), (tag, label, text)
            at(frame[2] - 46, frame[3] - 25)
            wait_for(lambda: active_frame()[0] == 'Classic-demo', 'real Cancel at resize floor')
            assert state() == 'Documents 755', state()
            print(f'{scale:g}x at minimum: scrolled to Free space, both buttons stayed visible, real Cancel worked', flush=True)
            return

        if stationary:
            assert output['currentModeId'] == next(m['id'] for m in output['modes'] if m['size'] == {'width': 800, 'height': 600})

            def status():
                current, = json.loads(user('kscreen-doctor -j'))['outputs']
                assert (current['currentModeId'], current['scale']) == (output['currentModeId'], scale), current

            assert sum(c == (212, 208, 200) for c in general.getdata()) < general.width * general.height // 8
            assert (name_box(general, scale)[3] - name_box(general, scale)[1]) / scale > 30, 'current font is not visibly enlarged'
            edit('sunset', general)
            check_name(capture('edited-current'), scale, out / 'edited-current-name.png', 'sunset')
            for index, mode in enumerate(('windows', 'current')):
                switch(mode)
                status()
                frame = active_frame()[1]
                tag = f'{mode}-{index}'
                assert observe_frame(scale, tag, fresh=False) == ident
                image = capture(tag)
                classic_skin = sum(c == (212, 208, 200) for c in image.getdata()) >= image.width * image.height // 8
                assert classic_skin == (mode == 'windows'), (tag, classic_skin)
                check_name(image, scale, out / f'{tag}-name.png', 'sunset')
                key('KEY_LEFTCTRL', 'KEY_TAB')
                permissions = capture(f'{tag}-permissions-page')
                labels = permissions.crop((round(12 * scale), round(72 * scale), permissions.width * 2 // 5,
                                           round(275 * scale)))
                observed = words(labels, out / f'{tag}-permissions-ocr.png', psm='6')
                assert {'Owner', 'Group'} <= observed.keys(), (tag, observed)
                key('KEY_LEFTCTRL', 'KEY_TAB')
                details = capture(f'{tag}-details-page')
                stamps = details.crop((0, round(65 * scale), details.width - round(15 * scale), round(235 * scale)))
                observed = words(stamps, out / f'{tag}-details-ocr.png', psm='6')
                assert {'Modified', 'Accessed'} <= observed.keys(), (tag, observed)
                key('KEY_LEFTCTRL', 'KEY_TAB')
                check_name(capture(f'{tag}-general'), scale, out / f'{tag}-general-name.png', 'sunset')
                assert state() == 'Documents 755', state()
            image = capture('pending-before-cancel')
            check_name(image, scale, out / 'cancel-field.png', 'sunset')
            at(frame[2] - 40, frame[3] - 25)
            wait_for(lambda: active_frame()[0] == 'Classic-demo', 'real Cancel on the stationary small output')
            assert state() == 'Documents 755', state()
            print(f'{scale:g}x stationary 800×600: same modal, tabs worked, real Cancel left {state()}', flush=True)
            return

        if not fresh_tight:
            check_general(general, scale)
            at(40, 77)
            wait_for(lambda: active_frame()[0] == 'Select Icon', 'KDE icon picker')
            shot(out / 'icon-picker.png')
            key('KEY_ESC')
            wait_for(lambda: active_frame()[0] == 'Properties for Documents', 'return from icon picker')
            assert state() == 'Documents 755', state()
        if scale == 1 and not fresh_tight:
            at(107, 37)
            capture('permissions')
            at(178, 37)
            capture('details')
            at(36, 37)
        edit('Discarded', general)
        check_name(capture('pending-before-cancel'), scale, out / 'cancel-field.png', 'Discarded')
        assert state() == 'Documents 755', state()
        at(frame[2] - 47, frame[3] - 23)
        wait_for(lambda: active_frame()[0] == 'Classic-demo', 'Cancel to close')
        assert state() == 'Documents 755', state()
        frame = open_properties()
        observe_frame(scale, 'fresh save', fresh=True)
        edit('Saved', capture('before-save-edit'))
        check_name(capture('pending-before-save'), scale, out / 'save-field.png', 'Saved')
        assert state() == 'Documents 755', state()
        at(frame[2] - 130, frame[3] - 23)
        wait_for(lambda: active_frame()[0] == 'Classic-demo' and state() == 'Saved 755', 'KIO to save and close')
        print(f'{scale:g}x edit remained pending; Cancel discarded it, OK committed it and closed', flush=True)
    finally:
        user(f'systemctl --user stop {unit}; rm -r {root}')


def profile(command):
    source = Path(__file__).with_name('properties_profile.py').read_text()
    return user(f"python - {command} <<'PY'\n{source}\nPY")


def recover_current(saved, *, packaged):
    try:
        toggle('current', packaged=packaged)
        # A failed switch can leave the mode marker current but parts of Windows active.
        user(f'set -e; test "$({executable("win7-classic", packaged)} status)" = current; '
             'state=${XDG_STATE_HOME:-$HOME/.local/state}/win7-classic; '
             'if test -e "$state/appearance"; then test "$(cat "$state/appearance")" = current; fi; '
             'systemctl --user is-active --quiet plasma-plasmashell.service')
        profile(f'restore {saved} config')
        user('dbus-send --session --type=signal /KDEPlatformTheme org.kde.KDEPlatformTheme.refreshFonts')
        profile(f'verify {saved}')
        # Keep the switcher's fresh current keys until recovery is verified. A stale (or
        # absent) pre-test copy is not a viable recovery source while Windows is active.
        profile(f'restore {saved} keys')
    except Exception as failure:
        raise RuntimeError(f'Original settings retained at {saved}; switcher recovery keys left in place') from failure
    else:
        user(f'rm -r -- {saved}')


def run_checks(out, output, *, packaged, stationary=False, tight=False):
    name = output['name']
    small = next(m['id'] for m in output['modes'] if m['size'] == {'width': 800, 'height': 600})
    if stationary:
        toggle('current', packaged=packaged)
        user("kwriteconfig6 --group General --key font 'Noto Sans,17,-1,5,400,0,0,0,0,0,0,0,0,0,0,1'")
    for scale in (1, 1.5):
        mode = small if (stationary or tight) else output['currentModeId']
        user(f'kscreen-doctor output.{name}.mode.{mode} output.{name}.scale.{scale}')
        current, = json.loads(user('kscreen-doctor -j'))['outputs']
        assert (current['currentModeId'], current['scale']) == (mode, scale), current
        toggle('windows', packaged=packaged)
        if stationary:
            toggle('current', packaged=packaged)  # Apply the test font before opening a modal.
            assert user('kreadconfig6 --group General --key font').startswith('Noto Sans,17,')
        exercise(out / f'{scale:g}', scale, current, stationary=stationary, fresh_tight=tight, packaged=packaged)
        if tight:
            exercise(out / f'{scale:g}' / 'resize', scale, current, resize=True, packaged=packaged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--installed', action='store_true')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--stationary-only', action='store_true', help='17-point mode switches on an already-small output, no geometry writes')
    selection.add_argument('--fresh-fit-only', action='store_true', help='open on an already-small output without moving/resizing any windows')
    parser.add_argument('--baseline', type=Path, help='apply the same visual checks to a cropped baseline (expected failure)')
    args = parser.parse_args()
    if args.baseline:
        check_general(Image.open(args.baseline).convert('RGB'), 1)
        return
    native = Image.open(ROOT / 'reference/screenshots/w7-properties.png').convert('RGB').crop((470, 250, 837, 724))
    check_general(native, 1, native=True)
    vmctl.start(VM)
    assert user('/usr/bin/win7-classic status') == 'current', 'Start the lab in current mode to back up its live appearance'
    output, = json.loads(user('kscreen-doctor -j'))['outputs']
    # A normal switch replaces profiles/current; even stale keys or their absence matter.
    saved = shlex.quote(profile('backup'))
    packaged = True
    try:
        if not args.installed:
            install(reset=False)
            packaged = False
        if args.stationary_only:
            run_checks(args.out, output, stationary=True, packaged=packaged)
        elif args.fresh_fit_only:
            run_checks(args.out, output, tight=True, packaged=packaged)
        else:
            run_checks(args.out / 'normal', output, packaged=packaged)
            run_checks(args.out / 'fresh-tight', output, tight=True, packaged=packaged)
            run_checks(args.out / 'stationary', output, stationary=True, packaged=packaged)
    finally:
        try:
            user(f'kscreen-doctor output.{output["name"]}.mode.{output["currentModeId"]} output.{output["name"]}.scale.{output["scale"]}')
        finally:
            recover_current(saved, packaged=packaged)


if __name__ == '__main__':
    main()
