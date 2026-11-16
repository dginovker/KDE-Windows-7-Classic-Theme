#!/usr/bin/env python3
"""Acceptance test for Classic window frames and colors (issue #9), run from the host against the lab VM.

A Qt fixture window gets the same geometry as the Windows reference window, and every frame pixel must equal
the reference except the app icon and title text (different apps and font). The caption gradient may differ
by 1 per channel: Windows truncates the interpolation, Qt rounds it.
"""
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, vmctl, user, toggle, kwin_script, kwin_query, wait_for, install, shot

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-frames-test')
REF = ROOT / 'reference/screenshots'
kconfig = SourceFileLoader('kconfig', str(ROOT / 'toggle/kconfig-keys')).load_module()
WINDOW = (256, 120, 768, 560)  # x, y, width, height of the reference window
CLIENT = (260, 143, 1020, 676)
ICON, TEXT, GRADIENT = (262, 125, 278, 141), (279, 124, 430, 142), (280, 124, 966, 142)


def frame_diff(ours, reference, region, masks, tolerant=()):
    """Pixels in region (minus masks) that differ; inside tolerant boxes a 1-per-channel difference is allowed."""
    a, b = Image.open(ours).convert('RGB'), Image.open(reference).convert('RGB')
    bad = []
    x0, y0, x1, y1 = region
    for y in range(y0, y1):
        for x in range(x0, x1):
            if any(l <= x < r and t <= y < bt for l, t, r, bt in masks):
                continue
            pa, pb = a.getpixel((x, y)), b.getpixel((x, y))
            limit = 1 if any(l <= x < r and t <= y < bt for l, t, r, bt in tolerant) else 0
            if max(abs(i - j) for i, j in zip(pa, pb)) > limit:
                bad.append((x, y, pa, pb))
    return bad


def assert_frame(name, reference, region, masks, tolerant=()):
    shot(OUT / f'{name}.png')
    bad = frame_diff(OUT / f'{name}.png', REF / reference, region, masks, tolerant)
    assert not bad, f'{name}: {len(bad)} frame pixels differ from {reference}, e.g. (x, y, ours, windows) {bad[:6]}'
    print(f'{name}: frame matches {reference}')


def fixture(geometry, activate=True):
    x, y, w, h = geometry
    kwin_script('for (const w of workspace.windowList()) if (w.caption == "Classic-demo") {'
                f' w.frameGeometry = {{x: {x}, y: {y}, width: {w}, height: {h}}};'
                + (' workspace.activeWindow = w; }' if activate else ' }'))


def fixture_state():
    rows = kwin_query('for (const w of workspace.windowList()) if (w.caption == "Classic-demo") emit(w.minimized, w.maximizeMode);')
    return '\t'.join(rows[-1]) if rows else 'gone'


def start_fixture():
    vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_window.py'), '/tmp/fixture_window.py')
    vmctl.run(VM, 'chmod 644 /tmp/fixture_window.py', 10)
    user('pkill -f "^/usr/bin/python3 /tmp/fixture_window.py"; rm -f /tmp/fixture-palette.json; systemd-run --user --collect -q python3 /tmp/fixture_window.py; true')
    wait_for(lambda: fixture_state() != 'gone', 'fixture window')


def config_snapshot():
    snapshot = {}
    for name in ('kdeglobals', 'kwinrc'):
        vmctl.transfer(VM, 'get', f'/tmp/win7-{name}', f'/home/tester/.config/{name}')
        snapshot[name] = kconfig.parse(Path(f'/tmp/win7-{name}'))
    return snapshot


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    vmctl.start(VM)
    install()
    before = config_snapshot()
    start_fixture()  # opened in current mode: it must change live
    font = lambda: user('cat /tmp/fixture-font.txt')
    wait_for(lambda: not font().startswith('Tahoma'), 'fixture reporting its current-mode font')
    toggle('windows')
    wait_for(lambda: font() == 'Tahoma 11', 'running app switching to Tahoma 11px')
    print('already-running app switched to Tahoma 11px without restarting')
    fixture(WINDOW)
    vmctl.pointer(VM, 100, 400)
    time.sleep(1.5)
    x, y, w, h = WINDOW
    window = (x, y, x + w, y + h)
    assert_frame('1-active', 'w7-taskbar.png', window, [CLIENT, ICON, TEXT], [GRADIENT])
    # Glyph edges are anti-aliased differently until issue #11, so "text" here is any clearly light pixel.
    text_rows = lambda path: sorted({y for y in range(TEXT[1], TEXT[3]) for x in range(TEXT[0], TEXT[2])
                                     if min(Image.open(path).convert('RGB').getpixel((x, y))) > 120})
    assert text_rows(OUT / '1-active.png') == text_rows(REF / 'w7-taskbar.png'), \
        f'title text rows {text_rows(OUT / "1-active.png")} differ from Windows {text_rows(REF / "w7-taskbar.png")}'
    print('title text sits on the same rows as Windows')

    vmctl.pointer(VM, 100, 400, 'left')  # click the desktop: the window goes inactive
    time.sleep(1.5)
    assert_frame('2-inactive', 'w7-inactive.png', window, [CLIENT, ICON, TEXT], [GRADIENT])

    fixture(WINDOW)
    vmctl.pointer(VM, 1009, 132)
    vmctl.button(VM, 'left', True)
    time.sleep(1)
    # The Windows reference shows the mouse pointer over the glyph; compare the button above and left of it.
    assert_frame('3-close-pressed', 'w7-close-pressed.png', (1002, 126, 1018, 131), [])
    shot(OUT / '3-close-pressed.png')
    bad = frame_diff(OUT / '3-close-pressed.png', REF / 'w7-close-pressed.png', (1002, 126, 1004, 140), [])
    assert not bad, f'pressed bevel left edge differs: {bad[:6]}'
    vmctl.pointer(VM, 100, 400)
    time.sleep(0.5)
    assert_frame('3-close-outside', 'w7-taskbar.png', (1002, 126, 1018, 140), [])
    vmctl.pointer(VM, 1009, 132)
    time.sleep(0.5)
    assert_frame('3-close-reenter', 'w7-close-pressed.png', (1002, 126, 1018, 131), [])
    vmctl.pointer(VM, 100, 400)
    vmctl.button(VM, 'left', False)  # released off the button: the window must stay open
    time.sleep(1)
    assert fixture_state() != 'gone', 'releasing a pressed close button outside it closed the window'

    fixture(WINDOW)
    vmctl.pointer(VM, 993, 132, 'left')
    wait_for(lambda: fixture_state().endswith('\t3'), 'maximize button maximizes')
    vmctl.pointer(VM, 640, 400)
    time.sleep(1.5)
    assert_frame('4-maximized', 'w7-maximized.png', (0, 0, 1280, 19), [(2, 1, 18, 17), (19, 0, 170, 18)], [(20, 0, 1226, 18)])
    vmctl.pointer(VM, 1251, 8, 'left')
    wait_for(lambda: fixture_state().endswith('\t0'), 'restore button restores')

    fixture(WINDOW)
    vmctl.pointer(VM, 975, 132, 'left')
    wait_for(lambda: fixture_state().startswith('true'), 'minimize button minimizes')
    print('caption buttons maximize, restore and minimize')

    # Controls: the window whose client area lines up with the native control reference.
    kwin_script('for (const w of workspace.windowList()) if (w.caption == "Classic-demo") { w.minimized = false; workspace.activeWindow = w; }')
    fixture((140, 100, 1000, 560))
    vmctl.pointer(VM, 1200, 700)
    time.sleep(1.5)
    shot(OUT / '5-controls.png')
    native = Image.open(REF / 'controls-native-client.png').convert('RGB')
    ours = Image.open(OUT / '5-controls.png').convert('RGB').crop((144, 123, 144 + 992, 123 + 533))
    pair = Image.new('RGB', (992, 533 * 2 + 8), 'white')
    pair.paste(native, (0, 0))
    pair.paste(ours, (0, 541))
    pair.save(OUT / 'controls-side-by-side.png')

    user('systemd-run --user --collect -q gtk3-demo')
    time.sleep(4)
    shot(OUT / '6-gtk.png')
    user('pkill -x gtk3-demo; true')

    vmctl.pointer(VM, 1009, 132)
    fixture(WINDOW)
    vmctl.pointer(VM, 1009, 132, 'left')
    wait_for(lambda: fixture_state() == 'gone', 'close button closes the window')
    print('close button closes the window')

    toggle('current')
    start_fixture()
    fixture(WINDOW)
    time.sleep(1.5)
    shot(OUT / '7-current.png')
    user('pkill -f "^/usr/bin/python3 /tmp/fixture_window.py"; true')
    after = config_snapshot()
    assert after == before, 'kdeglobals/kwinrc differ after windows -> current: ' + str(
        {f: {g: (before[f].get(g), after[f].get(g)) for g in set(before[f]) | set(after[f]) if before[f].get(g) != after[f].get(g)} for f in before})
    print('current mode kdeglobals and kwinrc restored exactly')
    print('ALL FRAME CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
