#!/usr/bin/env python3
"""Exercise the packaged Classic tray and stock applet shortcut recorder in the lab."""
import argparse
from io import BytesIO
from pathlib import Path
import re
import subprocess
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, digest, shot, user, vmctl, wait_for
from test_calendar import is_open
from test_taskbar import FACE, SHADOW, WHITE, tray_left

REFERENCE = ROOT / 'reference/screenshots/w7-notification-area.png'
SINK = '@DEFAULT_AUDIO_SINK@'
APPLET_CONFIG = '~/.config/plasma-org.kde.plasma.desktop-appletsrc'


def icon_center(image, reference, box):
    tile = reference.crop(box)
    w, h = tile.size
    expected = tile.tobytes()
    hits = [(x + w // 2, y + h // 2) for x in range(tray_left(image), 1220)
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
    group = re.search(r'(?m)^(\[Containments\].*\[Applets\]\[\d+\])\n[^\[]*?^plugin=org\.kde\.plasma\.notifications$', layout)
    assert group, 'Notifications is not in the live applet config'
    return f'{group[1]}[Shortcuts]\nglobal={shortcut}' in layout


def main(out, function_key):
    keys = ('KEY_LEFTMETA', 'KEY_LEFTSHIFT', 'KEY_' + function_key)
    shortcut = 'Meta+Shift+' + function_key
    out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    assert user('/usr/bin/win7-classic status') == 'current'
    assert '"scale":1' in user('kscreen-doctor -j').replace(' ', ''), 'start from stock lab at 100%'
    before = digest()
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
        crop = (875, 600, 1280, 747)
        click(marker)
        wait_for(lambda: ImageChops.difference(image.crop(crop), snap('overflow-pointer').crop(crop)).getbbox(), 'marker opens overflow')
        key('KEY_ESC')
        wait_for(lambda: snap('overflow-dismissed').crop(crop).tobytes() == image.crop(crop).tobytes(), 'Escape closes overflow')
        print('Genuine marker, speaker, 24px pitch, single sunken frame; native mute and overflow')

        click(marker, 'right')
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
        user('notify-send -a Kate -t 1500 -h string:desktop-entry:org.kde.kate "W39-Shortcut" "Native activation proof"')
        time.sleep(3)
        key(*keys)
        wait_for(lambda: any('W39-Shortcut' in word for word, _ in words('shortcut-history')),
                 'real history opened by the saved shortcut')
        click((810, 540))
        print('Real recorder stages then applies Notifications shortcut; hardware chord opens native history')

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
    print('150% calendar and byte-identical current layout')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--key', choices=[f'F{i}' for i in range(1, 13)], default='F10',
                        help='unused Meta+Shift function key for the real recorder')
    args = parser.parse_args()
    main(args.out, args.key)
