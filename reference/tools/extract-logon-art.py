#!/usr/bin/env python3
"""Extract only the logon artwork from a local, genuine Windows 7 Ultimate reference.

Pass paths to imageres.dll, authui.dll and basebrd.dll (in that order). Do not retain
or distribute the source binaries with the theme. Requires Pillow and wrestool.
"""
from pathlib import Path
import io
import struct
import subprocess
import sys

from PIL import Image

PLASMA = Path(__file__).resolve().parents[2] / 'plasma'


def resource(file, kind, number):
    return subprocess.check_output(['wrestool', '-x', '-t', kind, '-n', str(number), str(file)])


def bitmap(file, number):
    data = resource(file, '2', number)
    off, = struct.unpack_from('<I', data, 10)
    w, h, _, depth = struct.unpack_from('<iiHH', data, 18)
    if depth != 32:
        raise ValueError(f'{number}: expected a 32-bit bitmap, not {depth}')
    return Image.frombytes('RGBA', (w, abs(h)), data[off:], 'raw', 'BGRA', 0, -1 if h > 0 else 1)


def main(imageres, authui, basebrd):
    shared = PLASMA / 'logon/art'
    sddm = PLASMA / 'sddm/art'
    shared.mkdir(exist_ok=True)
    sddm.mkdir(exist_ok=True)
    jpg = subprocess.check_output(['wrestool', '-x', '--raw', '-t', '+IMAGE', '-n', '5035', imageres])
    with Image.open(io.BytesIO(jpg)) as image:
        if image.format != 'JPEG' or image.size != (1440, 900):
            raise ValueError('5035: expected the genuine 16:10 logon JPEG')
    (shared / 'background.jpg').write_bytes(jpg)
    bitmap(basebrd, 120).save(shared / 'branding.png')
    for name, number in {
        'tile': 12223, 'submit': 12288, 'submit-down': 12287,
        'button': 12263, 'button-down': 12262,
    }.items():
        bitmap(authui, number).save(shared / f'{name}.png')
    for name, number in {'power': 12316, 'power-down': 12317, 'power-icon': 12215}.items():
        bitmap(authui, number).save(sddm / f'{name}.png')


if __name__ == '__main__':
    main(*sys.argv[1:])
