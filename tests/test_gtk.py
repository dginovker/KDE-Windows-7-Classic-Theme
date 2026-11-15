#!/usr/bin/env python3
"""GTK 3 in Windows mode (issue #12), run from the host against the lab VM.

GTK draws its own controls, so the check is on the Classic signature pixels of each control (bevel colors on
the right sides of the box) rather than whole-image equality; screenshots go to the issue for visual review.
"""
from pathlib import Path
import sys
import time

from PIL import Image

from lab import ROOT, VM, vmctl, user, toggle, kwin_query, kwin_script, wait_for, install, shot

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-gtk-test')
FACE, LIGHT, SHADOW, DARK, WHITE = (212, 208, 200), (255, 255, 255), (128, 128, 128), (64, 64, 64), (255, 255, 255)
GTK_STATE = ('gsettings get org.gnome.desktop.interface gtk-theme; gsettings get org.gnome.desktop.interface font-name; '
             'cd ~/.config && sha256sum gtk-3.0/settings.ini gtk-4.0/settings.ini gtk-3.0/gtk.css gtk-4.0/gtk.css gtk-3.0/colors.css gtk-4.0/colors.css 2>&1; true')


def fixture_open():
    return any(row[0] == 'GTK Classic-demo' for row in kwin_query('for (const w of workspace.windowList()) emit(w.caption);'))


def bevel_at(image, x0, y0, x1, y1):
    """Edge colors of a box: (top-left outer, bottom-right outer)."""
    return image.getpixel((x0, (y0 + y1) // 2)), image.getpixel((x1, (y0 + y1) // 2))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    vmctl.start(VM)
    install()
    before = user(GTK_STATE)
    vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_gtk.py'), '/tmp/fixture_gtk.py')
    vmctl.run(VM, 'chmod 644 /tmp/fixture_gtk.py', 10)
    user('pkill -f "^/usr/bin/python3 /tmp/fixture_gtk.py"; systemd-run --user --collect -q python3 /tmp/fixture_gtk.py')
    wait_for(fixture_open, 'GTK fixture window')

    toggle('windows')
    assert user('gsettings get org.gnome.desktop.interface gtk-theme') == "'Win7-Classic'", 'GTK theme not switched'
    time.sleep(2)  # the running GTK app restyles itself from the gsettings change
    kwin_script('for (const w of workspace.windowList()) if (w.caption == "GTK Classic-demo") { w.frameGeometry = {x: 140, y: 100, width: 1000, height: 580}; workspace.activeWindow = w; }')
    vmctl.pointer(VM, 1200, 700)
    time.sleep(1.5)
    shot(OUT / '1-windows.png')
    image = Image.open(OUT / '1-windows.png').convert('RGB')
    background = image.getpixel((900, 500))
    assert background == FACE, f'window background {background} is not Classic ButtonFace'
    # Find the "Normal" button's outer bevel along its middle row: white left edge, dark right edge.
    row = 0
    for y in range(140, 260):
        line = [image.getpixel((x, y)) for x in range(150, 330)]
        if line.count(LIGHT) > 3 and DARK in line:
            row = y
            break
    assert row, 'no Classic raised button bevel (white/dark edges) found in the GTK window'
    print(f'GTK button has a Classic raised bevel (row {row}); background is ButtonFace')
    whites = sum(1 for y in range(250, 520) for x in range(150, 900) if image.getpixel((x, y)) == WHITE)
    assert whites > 3000, 'entries/check boxes are not white sunken fields'

    toggle('current')
    time.sleep(2)
    shot(OUT / '2-current.png')
    after = user(GTK_STATE)
    theme_and_font = lambda state: state.splitlines()[:2]
    assert theme_and_font(after) == theme_and_font(before), f'GTK theme/font not restored: {theme_and_font(after)}'
    print('GTK theme and font restored')
    # KDE's GTK bridge regenerates ~/.config/gtk-*/ whenever KDE colors or the decoration change, and the first
    # time it also fills in its standard files. From then on a round trip must leave them byte-identical.
    toggle('windows')
    time.sleep(2)
    toggle('current')
    time.sleep(2)
    assert user(GTK_STATE) == after, f'GTK settings differ after a second round trip:\n{after}\n---\n{user(GTK_STATE)}'
    print('second round trip leaves all GTK settings files byte-identical')
    (OUT / 'first-use-changes.txt').write_text(user('cd ~/.config && for f in gtk-3.0/settings.ini gtk-4.0/settings.ini; do echo "== $f"; cat $f; done'))
    user('pkill -f "^/usr/bin/python3 /tmp/fixture_gtk.py"; true')

    native = Image.open(ROOT / 'reference/screenshots/controls-native-client.png').convert('RGB')
    ours = image.crop((144, 100, 144 + 992, 100 + 580))
    pair = Image.new('RGB', (992, 533 + 580 + 8), 'white')
    pair.paste(native, (0, 0))
    pair.paste(ours, (0, 541))
    pair.save(OUT / 'side-by-side.png')
    print('ALL GTK CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
