#!/usr/bin/env python3
"""Check the genuine footer crops without starting Qt or a desktop session."""
from pathlib import Path
import runpy
import tempfile
import unittest

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'reference/screenshots'
SHARED = ROOT / 'plasma/logon/art'
GREETER = ROOT / 'plasma/sddm/art'


class LogonFooterAssets(unittest.TestCase):
    def test_capture_assets_reproduce(self):
        extract = runpy.run_path(str(ROOT / 'reference/tools/extract-logon-controls.py'))
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)
            extract['main'](dest, dest)
            for original in (SHARED / 'accessibility.png', GREETER / 'power-main.png', GREETER / 'power-menu.png'):
                self.assertEqual((dest / original.name).read_bytes(), original.read_bytes(), original.name)

    def test_assets_recompose_genuine_controls(self):
        lock = Image.open(REF / 'w7-lock.png').convert('RGBA')
        login = Image.open(REF / 'w7-login.png').convert('RGBA')
        background = Image.open(SHARED / 'background.jpg').convert('RGBA').resize(lock.size, Image.Resampling.BICUBIC)
        for image, behind, expected, x in (
            (SHARED / 'accessibility.png', background, lock, 34),
            (SHARED / 'accessibility.png', background, login, 34),
            (GREETER / 'power-main.png', lock, login, 1188),
            (GREETER / 'power-menu.png', lock, login, 1226),
        ):
            with self.subTest(image=image.name):
                art = Image.open(image)
                box = (x, 738, x + art.width, 738 + art.height)
                actual = Image.alpha_composite(behind.crop(box), art).convert('RGB')
                difference = ImageChops.difference(actual, expected.crop(box).convert('RGB'))
                self.assertLessEqual(max(high for _, high in difference.getextrema()), 1)


if __name__ == '__main__':
    unittest.main()
