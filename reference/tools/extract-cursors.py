#!/usr/bin/env python3
"""Build plasma/cursors/Win7-Classic-Cursors from reference/cursors (Python + Pillow).

CUR images/hotspots and ANI frame order/jiffy timing are preserved at 32 and 48px.
The input is the default Windows 7 scheme extracted offline from the reference VM;
USER32's built-in I-beam/crosshair supply the scheme's blank registry entries.
Xcursor stores premultiplied ARGB, unlike Windows' straight-alpha BGRA.
"""
from pathlib import Path
import shutil
import struct

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'reference/cursors'
THEME = ROOT / 'plasma/cursors/Win7-Classic-Cursors'
# Windows has no separate copy/alias/grab glyph in its default scheme; these use normal/link/move selection.
ROLES = {
    'aero_arrow.cur': 'default arrow left_ptr top_left_arrow context-menu copy dnd-copy alias link 1081e37283d90000800003c07f3ef6bf 6407b0e94181790501fd1e167b474872 b66166c04f8c3109214a4fbd64a50fc8 3085a0e285430894940527032f8b26df 640fb0e74195791501fd1ed57b41487f a2a266d0498c3104214a47bd64ab0fc8',
    'user32-ibeam.cur': 'text xterm ibeam vertical-text',
    'user32-crosshair.cur': 'crosshair cross tcross cell plus',
    'aero_busy.ani': 'wait watch',
    'aero_working.ani': 'progress left_ptr_watch half-busy 00000000000000020006000e7e9ffc3f 08e8e1c95fe2fc01f976f1e063a24ccd 3ecb610c1bf2410f44200f48c40d3599',
    'aero_link.cur': 'pointer pointing_hand hand1 hand2 grab openhand 9d800788f1b08800ae810202380a0822 e29285e634086352946a0e7090d73106',
    'aero_ew.cur': 'ew-resize e-resize w-resize size_hor size-hor h_double_arrow sb_h_double_arrow col-resize split_h',
    'aero_ns.cur': 'ns-resize n-resize s-resize size_ver size-ver v_double_arrow sb_v_double_arrow row-resize split_v 00008160000006810000408080010102',
    'aero_nwse.cur': 'nwse-resize nw-resize se-resize size_fdiag size-fdiag',
    'aero_nesw.cur': 'nesw-resize ne-resize sw-resize size_bdiag size-bdiag',
    'aero_move.cur': 'move fleur size_all all-scroll grabbing closedhand dnd-move dnd-none 4498f0e0c1937ffe01fd06f973665830 9081237383d90e509aa00f00170e968f fcf21c00b30f7e3f83fe0dfd12e71cff',
    'aero_unavail.cur': 'not-allowed no-drop forbidden circle crossed_circle 03b6e0fcb3499374a867c041f52298f0',
    'aero_helpsel.cur': 'help whats_this question_arrow left_ptr_help 5c6cd98b3f3ebcb1f9c7f1c204630408 d9ce0ab605698f320427677b458ad60b',
    'aero_pen.cur': 'pencil',
    'aero_up.cur': 'up_arrow',
    # Windows has no magnifying cursor; use its precision-selection cursor.
}
ROLES['user32-crosshair.cur'] += ' zoom-in zoom-out'


def cur_images(data):
    reserved, kind, count = struct.unpack_from('<HHH', data)
    if reserved or kind != 2:
        raise ValueError('expected Windows CUR data')
    for i in range(count):
        w, h, _, _, hx, hy, length, offset = struct.unpack_from('<BBBBHHII', data, 6 + i * 16)
        w, h = w or 256, h or 256
        blob = data[offset:offset + length]
        header, bw, bh, planes, bits = struct.unpack_from('<IiiHH', blob)
        if header != 40 or bw != w or bh != h * 2 or planes != 1 or bits not in (1, 4, 32):
            raise ValueError(f'unsupported cursor DIB: {w}x{h}, {bits}bpp')
        stride = ((w * bits + 31) // 32) * 4
        palette = [tuple(blob[p:p + 3][::-1]) for p in range(header, header + (4 << bits), 4)] if bits < 32 else []
        start = header + len(palette) * 4
        xor = blob[start:start + stride * h]
        mask = blob[start + stride * h:]
        if bits == 32:
            image = Image.frombytes('RGBA', (w, h), xor, 'raw', 'BGRA', stride, -1)
        else:
            image = Image.new('RGBA', (w, h))
            inverse = Image.new('L', (w, h))
            for y in range(h):
                for x in range(w):
                    bit = 7 - x % 8
                    a = (mask[(h - 1 - y) * ((w + 31) // 32 * 4) + x // 8] >> bit) & 1
                    shift = 8 - bits - (x * bits) % 8
                    index = (xor[(h - 1 - y) * stride + (x * bits) // 8] >> shift) & ((1 << bits) - 1)
                    color = palette[index]
                    if a and color != (0, 0, 0):
                        if color != (255, 255, 255):
                            raise ValueError('unsupported colored XOR cursor pixel')
                        inverse.putpixel((x, y), 255)
                    elif not a:
                        image.putpixel((x, y), color + (255,))
            # Xcursor cannot invert backgrounds: black matches white fields; a white rim keeps dark fields legible.
            rim = inverse.filter(ImageFilter.MaxFilter(3))
            image.paste((255, 255, 255, 255), mask=rim)
            image.paste((0, 0, 0, 255), mask=inverse)
        yield image, hx, hy


def chunks(data):
    offset = 0
    while offset < len(data):
        tag, size = struct.unpack_from('<4sI', data, offset)
        yield tag, data[offset + 8:offset + 8 + size]
        offset += 8 + size + size % 2


def frames(path):
    data = path.read_bytes()
    if path.suffix == '.cur':
        return [(list(cur_images(data)), 0)]
    if data[:4] != b'RIFF' or data[8:12] != b'ACON':
        raise ValueError(f'{path}: expected ANI RIFF/ACON')
    parts = dict(chunks(data[12:]))
    _, count, steps, _, _, _, _, rate, flags = struct.unpack('<9I', parts[b'anih'])
    icons = [list(cur_images(blob)) for tag, blob in chunks(parts[b'LIST'][4:]) if tag == b'icon']
    sequence = struct.unpack(f'<{steps}I', parts[b'seq ']) if flags & 2 else range(steps)
    rates = struct.unpack(f'<{steps}I', parts[b'rate']) if b'rate' in parts else [rate] * steps
    if len(icons) != count:
        raise ValueError(f'{path}: ANI frame count mismatch')
    return [(icons[index], round(jiffies * 1000 / 60)) for index, jiffies in zip(sequence, rates)]


def xcursor(path):
    images = [(im, hx, hy, delay) for variants, delay in frames(path) for im, hx, hy in variants]
    toc, payload = [], bytearray()
    for im, hx, hy, delay in images:
        size = max(im.size)
        toc.append(struct.pack('<III', 0xfffd0002, size, 16 + 12 * len(images) + len(payload)))
        payload += struct.pack('<9I', 36, 0xfffd0002, size, 1, im.width, im.height, hx, hy, delay)
        for r, g, b, a in im.getdata():
            payload += struct.pack('<I', a << 24 | ((r * a + 127) // 255) << 16 | ((g * a + 127) // 255) << 8 | (b * a + 127) // 255)
    return struct.pack('<4sIII', b'Xcur', 16, 0x10000, len(images)) + b''.join(toc) + payload


def main():
    shutil.rmtree(THEME, ignore_errors=True)
    (THEME / 'cursors').mkdir(parents=True)
    (THEME / 'index.theme').write_text('[Icon Theme]\nName=Windows 7 Cursors\nComment=Genuine Windows 7 default cursor scheme\n')
    for filename, names in ROLES.items():
        primary, *aliases = names.split()
        (THEME / 'cursors' / primary).write_bytes(xcursor(SOURCE / filename))
        for name in aliases:
            (THEME / 'cursors' / name).symlink_to(primary)
    print('Built', THEME)


if __name__ == '__main__':
    main()
