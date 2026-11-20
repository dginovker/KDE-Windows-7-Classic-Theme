#!/usr/bin/env python3
"""Exercise the packaged Classic tray and stock applet shortcut recorder in the lab."""
import argparse
from io import BytesIO
from pathlib import Path
import re
import subprocess
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, digest, kwin_query, shot, user, vmctl, wait_for
from test_calendar import is_open
from test_taskbar import FACE, SHADOW, WHITE, tray_left

REFERENCE = ROOT / 'reference/screenshots/w7-notification-area.png'
SINK = '@DEFAULT_AUDIO_SINK@'
APPLET_CONFIG = '~/.config/plasma-org.kde.plasma.desktop-appletsrc'


QICON = '''from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
app = QApplication([])
assert QIcon.themeName() == 'Win7-Classic', QIcon.themeName()
names = ['audio-volume-medium-symbolic', 'audio-volume-muted-symbolic',
         'network-wired-disconnected-symbolic', 'arrow-up-symbolic']
def icons():
    result = []
    for name in names:
        icon = QIcon.fromTheme(name)
        assert not icon.isNull(), name
        result.append(icon.pixmap(24, 24).toImage())
    return result
classic = icons()
QIcon.setThemeName('breeze')
for name, themed, stock in zip(names, classic, icons()):
    assert themed == stock, name
    print(name + ': exact Breeze pixels at 24px in a Qt Widgets process')
'''


def icon_center(image, reference, box, *, tray_start=None):
    tile = reference.crop(box)
    w, h = tile.size
    expected = tile.tobytes()
    hits = [(x + w // 2, y + h // 2) for x in range(tray_left(image) if tray_start is None else tray_start, 1220)
            for y in range(764, 784) if image.crop((x, y, x + w, y + h)).tobytes() == expected]
    assert len(hits) == 1, f'genuine tile at {box} expected exactly once, found {hits}'
    return hits[0]


def ocr(image, region=None):
    left, top = (0, 0) if region is None else region[:2]
    zoom = 1 if region is None else 3
    if region is not None:
        image = image.crop(region)
        image = image.resize((image.width * zoom, image.height * zoom))
    png = BytesIO()
    image.save(png, 'PNG')
    result = subprocess.check_output(['tesseract', 'stdin', 'stdout', '--psm', '11', 'tsv'],
                                     input=png.getvalue(), stderr=subprocess.DEVNULL).decode()
    words = []
    for line in result.splitlines()[1:]:
        columns = line.split('\t')
        if len(columns) == 12 and columns[11]:
            x, y, w, h = map(int, columns[6:10])
            words.append((columns[11], (left + x // zoom, top + y // zoom, w // zoom, h // zoom)))
    return words


def label(words, name, where=lambda x, y: True):
    hits = [(x + w // 2, y + h // 2) for text, (x, y, w, h) in words
            if text == name and where(x + w // 2, y + h // 2)]
    assert len(hits) == 1, f'{name}: expected one matching label, found {hits}'
    return hits[0]


def has_shortcut(shortcut):
    layout = user(f'cat {APPLET_CONFIG}')
    # Assert the shortcut belongs to Notifications itself, not the tray or another applet.
    group = re.search(r'(?m)^(\[Containments\].*\[Applets\]\[\d+\])\n[^\[]*?^plugin=org\.win7classic\.notifications$', layout)
    assert group, 'Notifications is not in the live applet config'
    if f'{group[1]}[Shortcuts]\nglobal={shortcut}' in layout:
        return group[1].split('[')[-1].rstrip(']')
    return None


def main(out, function_key, remove_tray=False):
    keys = ('KEY_LEFTMETA', 'KEY_LEFTSHIFT', 'KEY_' + function_key)
    shortcut = 'Meta+Shift+' + function_key
    out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    assert user('/usr/bin/win7-classic status') == 'current'
    assert '"scale":1' in user('kscreen-doctor -j').replace(' ', ''), 'start from stock lab at 100%'
    before = digest()
    accel_file = '~/.config/kglobalshortcutsrc'
    accel = user(f'base64 -w0 {accel_file}')
    vol = user(f'wpctl get-volume {SINK}')
    reference = Image.open(REFERENCE).convert('RGB')

    def snap(name):
        path = out / f'{name}.png'
        shot(path)
        return Image.open(path).convert('RGB')

    def words(name, region=None):
        return ocr(snap(name), region)

    def click(pt, button='left'):
        vmctl.pointer(VM, *pt, button)

    def key(*codes):
        vmctl.keys(VM, *codes)

    try:
        user(f'wpctl set-volume {SINK} .40; wpctl set-mute {SINK} 0')
        print(user('/usr/bin/win7-classic windows'))
        vmctl.pointer(VM, 820, 690)
        time.sleep(2)
        image = snap('classic-idle')
        marker = icon_center(image, reference, (13, 17, 18, 25))
        speaker = icon_center(image, reference, (77, 15, 93, 31))
        assert speaker[0] > marker[0] and (speaker[0] - marker[0] - 22) % 24 == 0
        left = tray_left(image)
        assert [image.getpixel((left + i, 762)) for i in (0, 1, 2)] == [SHADOW, FACE, FACE]
        assert [image.getpixel((1277 - i, 762)) for i in (0, 1, 2)] == [WHITE, FACE, FACE]
        for state in (True, False):
            click(speaker, 'middle')
            wait_for(lambda: ('[MUTED]' in user(f'wpctl get-volume {SINK}')) == state, f'volume mute={state}')
        crop = (875, 355, 1280, 747)
        click(marker)
        wait_for(lambda: ImageChops.difference(image.crop(crop), snap('overflow-pointer').crop(crop)).getbbox(), 'marker opens overflow')
        click(marker)
        vmctl.pointer(VM, 820, 690)
        wait_for(lambda: snap('overflow-click-closed').crop(crop).tobytes() == image.crop(crop).tobytes(), 'same marker closes overflow')
        click(marker)
        wait_for(lambda: ImageChops.difference(image.crop(crop), snap('overflow-open-again').crop(crop)).getbbox(), 'marker reopens overflow')
        key('KEY_ESC')
        vmctl.pointer(VM, 820, 690)
        wait_for(lambda: snap('overflow-dismissed').crop(crop).tobytes() == image.crop(crop).tobytes(), 'Escape closes overflow')
        click(speaker)
        vmctl.pointer(VM, 820, 690)
        def classic_volume_open():
            for row in kwin_query('for (const w of workspace.windowList()) if (w.resourceClass === "org.kde.plasmashell" && !w.popupWindow) { const g=w.frameGeometry; emit(g.x,g.y,g.width,g.height); }'):
                x, y, w, h = map(float, row)
                if (w, h) == (70, 291) and abs(x + w / 2 - speaker[0]) <= 2:
                    popup = snap('volume-controls')
                    box = tuple(map(round, (x+1, y+h-43, x+w-1, y+h-1)))
                    return popup.getpixel((round(x+5), round(y+16))) == (255, 255, 255) and any(
                        word == 'Mixer' for word, _ in ocr(popup, box))
            return False

        wait_for(classic_volume_open, 'compact white vertical-slider volume popup opens over its genuine icon')
        click((820, 690))
        wait_for(lambda: snap('volume-click-away').crop(crop).tobytes() == image.crop(crop).tobytes(), 'volume click-away')
        print(user("systemd-run --user --wait --pipe --collect -q /usr/bin/python - <<'PYQT'\n" + QICON + "PYQT"))
        print('Genuine marker, speaker, 24px pitch, single sunken frame; native mute and overflow')

        live_marker = icon_center(snap('after-volume-idle'), reference, (13, 17, 18, 25))
        click(live_marker, 'right')
        time.sleep(1)
        items = words('items-before')
        _, y = label(items, 'Notifications')
        assigned = lambda: has_shortcut(shortcut)
        assert not assigned(), f'test key already configured: {shortcut}'
        click(label(items, 'None', lambda x, cy: x > 600 and abs(cy - y) < 10))
        key(*keys)
        time.sleep(1.5)
        snap('items-pending')
        assert not assigned(), 'the editor applied before confirmation'
        click(label(words('items-pending-buttons', (760, 650, 1060, 700)), 'Apply'))
        wait_for(assigned, 'stock shortcut editor saves the hosted applet shortcut')
        key('KEY_ESC')
        time.sleep(.7)
        print('Real recorder stages then applies the Notifications shortcut')
        if remove_tray:
            nid = assigned()
            call = 'busctl --user call org.kde.kglobalaccel /kglobalaccel org.kde.KGlobalAccel'
            binding = f"as 4 plasmashell 'activate widget {nid}' plasmashell 'Activate Notifications Widget'"
            keys_before_remove = user(f'{call} shortcutKeys {binding}')
            assert re.search(r' [1-9]\d*', keys_before_remove), keys_before_remove
            script = ('for (const p of panels()) for (const w of p.widgets()) '
                      'if (w.type === "org.win7classic.tray") w.remove()')
            user(f"qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript '{script}'")
            wait_for(lambda: 'plugin=org.win7classic.tray\n' not in user(f'cat {APPLET_CONFIG}') + '\n'
                     and 'plugin=org.win7classic.notifications\n' not in user(f'cat {APPLET_CONFIG}') + '\n',
                     'Plasma finalized tray and child removal')
            assert user(f'{call} shortcutKeys {binding}') == keys_before_remove, 'dormant registration was not reproduced'
            snap('tray-removed')
            print(f'Plasma finalized tray removal; KGlobalAccel still holds dormant widget {nid}: {keys_before_remove}')
        else:
            user('notify-send -a Kate -t 1500 -h string:desktop-entry:org.kde.kate "W39-Shortcut" "Native activation proof"')
            time.sleep(3)
            key(*keys)
            wait_for(lambda: {'disturb', 'W39-Shortcut'} <= {
                word for word, _ in words('shortcut-history', (800, 280, 1275, 754))
            }, 'real history, not just a toast, opened by the saved shortcut')
            click((810, 540))
            print('Hardware chord opens native notification history')

            user('kscreen-doctor output.Virtual-1.scale.1.5')
            time.sleep(2)
            click((1200, 770))
            wait_for(lambda: is_open(snap('scaled-calendar'), 1.5), '150% calendar remains anchored above the tray')
            key('KEY_ESC')
            wait_for(lambda: not is_open(snap('scaled-calendar-dismissed'), 1.5), '150% calendar dismissed')
    finally:
        user(f"wpctl set-volume {SINK} {vol.split()[1]}; wpctl set-mute {SINK} {int('[MUTED]' in vol)}")
        user('kscreen-doctor output.Virtual-1.scale.1')
        if user('/usr/bin/win7-classic status') == 'windows':
            print(user('/usr/bin/win7-classic current'))
    assert digest() == before, 'current layout bytes changed'
    if remove_tray:
        after = user(f'{call} shortcutKeys {binding}')
        assert after == 'a(ai) 0', f'Windows-only KGlobalAccel action survived tray removal: {after}'
    assert user(f'base64 -w0 {accel_file}') == accel, 'KGlobalAccel file bytes changed'
    print('Byte-identical current layout and settled KGlobalAccel metadata')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--key', choices=[f'F{i}' for i in range(1, 13)], default='F10',
                        help='unused Meta+Shift function key for the real recorder')
    parser.add_argument('--remove-tray', action='store_true', help='finalize removal in the disposable Windows profile')
    args = parser.parse_args()
    main(args.out, args.key, args.remove_tray)
