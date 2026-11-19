#!/usr/bin/env python3
"""Exercise the real Windows seed without a desktop, using an isolated XDG Desktop."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'toggle/windows/seed'
FILE = 'plasma-org.kde.plasma.desktop-appletsrc'
TRASH = 'plugin=org.kde.plasma.trash'
DESKTOP = '[Containments][1]\nlastScreen=0\nplugin=org.kde.plasma.folder\nwallpaperplugin=org.kde.image\n'


class RecycleBinSeed(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name)
        self.config = self.home / 'config'
        self.config.mkdir()
        self.desktop = self.home / 'My Desktop'
        self.desktop.mkdir()
        (self.config / 'user-dirs.dirs').write_text('XDG_DESKTOP_DIR="$HOME/My Desktop"\n')
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.config))

    def seed(self, text):
        path = self.config / FILE
        path.write_text(text)
        subprocess.run([SEED, self.config], env=self.env, check=True, capture_output=True, text=True)
        return path.read_text()

    def test_empty_folder_view_gets_one_stock_widget_and_no_files(self):
        original = '[ActionPlugins][0]\nMiddleButton;NoModifier=org.kde.paste\n\n' + DESKTOP
        marker = self.desktop / '.directory'
        marker.write_bytes(b'[Desktop Entry]\nName=Owner desktop\n')
        after = self.seed(original)
        self.assertEqual(after.count(TRASH), 1)
        self.assertRegex(after, r'\[Containments\]\[1\]\[Applets\]\[\d+\]\nplugin=org\.kde\.plasma\.trash\n')
        self.assertRegex(after, r'ItemGeometriesHorizontal=Applet-\d+:0,0,80,80,0;')
        self.assertIn('MiddleButton;NoModifier=org.kde.paste', after)
        self.assertEqual(list(self.desktop.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b'[Desktop Entry]\nName=Owner desktop\n')

    def test_existing_trash_widget_preserved_not_duplicated(self):
        widget = '\n[Containments][1][Applets][31]\n' + TRASH + '\nimmutability=2\n'
        original = DESKTOP + 'ItemGeometriesHorizontal=Applet-31:640,400,112,96,0;\n' + widget
        after = self.seed(original)
        self.assertEqual(after.count(TRASH), 1)
        self.assertIn(widget, after)
        self.assertIn('ItemGeometriesHorizontal=Applet-31:640,400,112,96,0;', after)

    def test_existing_trash_link_and_same_name_file_are_untouched(self):
        fixtures = {
            'Custom bin.desktop': b'[Desktop Entry]\nType=Link\nURL=trash:/\n',
            'Recycle Bin.desktop': b'owner data; do not overwrite\n',
        }
        for name, data in fixtures.items():
            (self.desktop / name).write_bytes(data)
        self.assertNotIn(TRASH, self.seed(DESKTOP))
        self.assertEqual({p.name: p.read_bytes() for p in self.desktop.iterdir()}, fixtures)

    def test_existing_arbitrary_widget_and_custom_folder_view_preserved(self):
        widget = ('\n[Containments][1][Applets][42]\nplugin=local.example.test\n\n'
                  '[Containments][1][Applets][42][Configuration][General]\ntext=keep me\n')
        after = self.seed(DESKTOP + 'ItemGeometriesHorizontal=Applet-42:0,0,112,96,0;\n' + widget)
        self.assertNotIn(TRASH, after)
        self.assertIn(widget, after)
        self.assertIn('ItemGeometriesHorizontal=Applet-42:0,0,112,96,0;', after)
        custom = '\n[Containments][1][General]\nurl=sftp://example.invalid/owner-desktop\n'
        after = self.seed(DESKTOP + custom)
        self.assertNotIn(TRASH, after)
        self.assertIn(custom, after)

    def test_mimeapps_keys_restore_exactly(self):
        path = self.config / 'mimeapps.list'
        before = b'[Default Applications]\nx-scheme-handler/trash=local.keep.desktop;\ntext/plain=org.kde.kate.desktop;\n'
        path.write_bytes(before)
        tool = ROOT / 'toggle/kconfig-keys'
        keys = ROOT / 'toggle/windows/keys'
        saved = self.home / 'current.json'
        subprocess.run([tool, 'save', keys, self.config, saved], check=True)
        subprocess.run([tool, 'load', keys, self.config], check=True, capture_output=True)
        self.assertIn(b'x-scheme-handler/trash=org.kde.dolphin.desktop;', path.read_bytes())
        subprocess.run([tool, 'load', saved, self.config], check=True, capture_output=True)
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
