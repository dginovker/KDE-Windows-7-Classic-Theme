#!/usr/bin/env python3
"""Stock presentation defaults update only the tray next to a Classic frame."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'toggle/windows'))
from tray_layout import migrate

FIXTURE = ROOT / 'tests/fixtures/legacy-quicklaunch-appletsrc'
FRAME = '[Containments][26][Applets][128]'
TRAY = '[Containments][26][Applets][83][General]'
MARKER = 'win7ClassicTrayDefaultsApplied=true\n'
DEFAULTS = 'reverseIconOrder=true\niconSpacing=1\n'


class TrayLayoutTests(unittest.TestCase):
    def test_targeted_insertions_and_no_repeat_after_reset_to_kde_defaults(self):
        old = FIXTURE.read_text().replace(TRAY.replace('][General]', '][Configuration][General]'), TRAY)
        changed = migrate(old)
        expected = old.replace(FRAME + '\n', FRAME + '\n' + MARKER).replace(TRAY + '\n', TRAY + '\n' + DEFAULTS)
        assert expected != old and TRAY in old and FRAME in old
        self.assertEqual(changed, expected)
        reset = changed.replace(DEFAULTS, '')
        self.assertEqual(migrate(reset), reset)

    def test_preserves_explicit_false_spacing_and_auto_size(self):
        saved = 'reverseIconOrder=false\niconSpacing=6\nscaleIconsToFit=true\n'
        old = FIXTURE.read_text().replace(TRAY.replace('][General]', '][Configuration][General]'), TRAY).replace(TRAY + '\n', TRAY + '\n' + saved)
        self.assertEqual(migrate(old), old.replace(FRAME + '\n', FRAME + '\n' + MARKER))
        qualified = old.replace('reverseIconOrder=false', 'reverseIconOrder[$i]=false')
        self.assertEqual(migrate(qualified), qualified.replace(FRAME + '\n', FRAME + '\n' + MARKER))

    def test_new_empty_tray_and_unrelated_panel(self):
        old = FIXTURE.read_text().replace(TRAY.replace('][General]', '][Configuration][General]'), TRAY).replace(TRAY, TRAY.replace('[83]', '[84]'))
        self.assertTrue(migrate(old).endswith('\n' + TRAY + '\n' + DEFAULTS))
        unrelated = old.replace('128;83', '83;128')
        self.assertEqual(migrate(unrelated), unrelated)


if __name__ == '__main__':
    unittest.main()
