#!/usr/bin/env python3
"""Issue #27: reproducible Xcursor binaries, source pixels/hotspots, aliases and ANI timing."""
import hashlib
from pathlib import Path
import runpy
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONVERTER = runpy.run_path(str(ROOT / 'reference/tools/extract-cursors.py'))
THEME = CONVERTER['THEME']


def images(path):
    data = path.read_bytes()
    magic, header, version, count = struct.unpack_from('<4sIII', data)
    assert (magic, header, version) == (b'Xcur', 16, 0x10000)
    result = []
    for i in range(count):
        kind, size, offset = struct.unpack_from('<III', data, 16 + 12 * i)
        h, t, s, v, w, ht, hx, hy, delay = struct.unpack_from('<9I', data, offset)
        assert (kind, h, t, s, v) == (0xfffd0002, 36, kind, size, 1)
        result.append((size, w, ht, hx, hy, delay, data[offset + 36:offset + 36 + w * ht * 4]))
    return result


class CursorAssets(unittest.TestCase):
    def test_reproducible(self):
        for source, names in CONVERTER['ROLES'].items():
            primary, *aliases = names.split()
            with self.subTest(source=source):
                path = THEME / 'cursors' / primary
                self.assertEqual(path.read_bytes(), CONVERTER['xcursor'](CONVERTER['SOURCE'] / source))
                variants = images(path)
                self.assertEqual({v[0] for v in variants}, {32, 48})
                for name in aliases:
                    alias = THEME / 'cursors' / name
                    self.assertTrue(alias.is_symlink())
                    self.assertEqual(alias.readlink(), Path(primary))

    def test_original_arrow_pixels_and_hotspot(self):
        # Independent oracle: the 32px CUR contains an uncompressed BGRA bitmap at its second directory entry.
        data = (CONVERTER['SOURCE'] / 'aero_arrow.cur').read_bytes()
        hx, hy, length, offset = struct.unpack_from('<HHII', data, 6 + 16 + 4)
        blob = data[offset:offset + length]
        expected = bytearray()
        for y in range(31, -1, -1):
            for x in range(32):
                b, g, r, a = blob[40 + (y * 32 + x) * 4:44 + (y * 32 + x) * 4]
                expected += bytes(((b * a + 127) // 255, (g * a + 127) // 255, (r * a + 127) // 255, a))
        actual = next(v for v in images(THEME / 'cursors/default') if v[0] == 32)
        self.assertEqual(actual[3:5], (hx, hy))
        self.assertEqual(actual[-1], expected)

    def test_animations(self):
        for role, delay in (('wait', 50), ('progress', 33)):
            for size in (32, 48):
                frames = [v for v in images(THEME / 'cursors' / role) if v[0] == size]
                self.assertEqual(len(frames), 18)
                self.assertEqual({v[5] for v in frames}, {delay})
                self.assertGreater(len({hashlib.sha256(v[-1]).digest() for v in frames}), 1)


if __name__ == '__main__':
    unittest.main()
