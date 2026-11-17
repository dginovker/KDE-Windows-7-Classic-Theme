#!/usr/bin/env python3
"""Existing Windows layouts upgrade without reseeding or rewriting unrelated KConfig bytes."""
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'toggle/windows'))
migration = SourceFileLoader('quicklaunch_migration', str(ROOT / 'toggle/windows/migrate-quicklaunch')).load_module()
from launchers import normalize_launchers

FIXTURE = ROOT / 'tests/fixtures/legacy-quicklaunch-appletsrc'
PINS = 'applications:org.kde.konsole.desktop,applications:firefox.desktop,applications:org.win7classic.explorer.desktop'
MERGED = PINS + ',applications:org.kde.kate.desktop'


class QuickLaunchMigrationTests(unittest.TestCase):
    def test_owner_structure_only_targeted_bytes_change_and_repeat_is_identical(self):
        original = FIXTURE.read_text()
        result, panels = migration.migrate(original)
        quick = original[original.index('[Containments][26][Applets][67]'):original.index('[Containments][26][Applets][28]')]
        expected = original.replace(quick, '').replace('launchers=' + PINS, 'launchers=' + MERGED).replace(
            'AppletOrder=127;67;28;90;128;83;129', 'AppletOrder=127;28;90;128;83;129')
        self.assertEqual(panels, ['26'])
        self.assertEqual(result, expected)
        self.assertEqual(migration.migrate(result), (result, []))
        self.assertIn('[Containments][26][Applets][83][Applets][84]', result)
        self.assertIn('# This deliberately unsorted custom configuration must stay verbatim.\nz=last\ntext=kept-123\na=first', result)

    def test_latest_classic_pin_order_is_preserved_before_quick_main_and_popup(self):
        original = FIXTURE.read_text().replace(PINS, 'applications:org.kde.kate.desktop,preferred://filemanager,applications:firefox.desktop')
        result, _ = migration.migrate(original)
        layout = migration.Layout(result)
        self.assertEqual(layout.get(('Containments', '26', 'Applets', '127', 'Configuration', 'General'), 'launchers'),
                         'applications:org.kde.kate.desktop,applications:org.win7classic.explorer.desktop,applications:firefox.desktop')

    def test_popup_only_and_multiple_quicklaunch_widgets_follow_panel_order(self):
        original = FIXTURE.read_text().replace('launcherUrls=file:///usr/share/applications/org.kde.dolphin.desktop,file:///usr/share/applications/firefox.desktop', 'launcherUrls=')
        extra = '\n[Containments][26][Applets][66]\nplugin=org.kde.plasma.quicklaunch\n\n[Containments][26][Applets][66][Configuration][General]\nlauncherUrls=applications:systemsettings.desktop\n'
        original = original.replace('127;67;28;', '127;66;67;28;') + extra
        result, _ = migration.migrate(original)
        self.assertIn('launchers=' + PINS + ',applications:systemsettings.desktop,applications:org.kde.kate.desktop', result)
        self.assertNotIn('plugin=org.kde.plasma.quicklaunch', result)
        self.assertIn('AppletOrder=127;28;90;128;83;129', result)

    def test_no_cross_panel_destination_and_two_independent_panels(self):
        original = FIXTURE.read_text()
        orphan = '\n[Containments][50]\nplugin=org.kde.panel\n\n[Containments][50][Applets][167]\nplugin=org.kde.plasma.quicklaunch\n\n[Containments][50][Applets][167][Configuration][General]\nlauncherUrls=applications:systemsettings.desktop\n'
        result, panels = migration.migrate(original + orphan)
        self.assertEqual(panels, ['26'])
        self.assertTrue(result.endswith(orphan))
        second = original.replace('[26]', '[50]').replace('[127]', '[227]').replace('[67]', '[167]').replace('127;67;', '227;167;')
        result, panels = migration.migrate(original + second)
        self.assertEqual(panels, ['26', '50'])
        self.assertNotIn('plugin=org.kde.plasma.quicklaunch', result)
        self.assertEqual(migration.migrate(result), (result, []))

    def test_ambiguous_destination_and_missing_pins_fail_without_rewrite(self):
        original = FIXTURE.read_text()
        ambiguous = original + '\n[Containments][26][Applets][130]\nplugin=org.win7classic.taskbar\n'
        for text in (ambiguous, original.replace('launchers=' + PINS + '\n', '')):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'appletsrc'
                path.write_text(text)
                with self.assertRaises(ValueError):
                    migration.main(path)
                self.assertEqual(path.read_text(), text)

    def test_check_validates_without_writing_before_recovery_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'appletsrc'
            path.write_bytes(FIXTURE.read_bytes())
            with redirect_stdout(io.StringIO()) as output:
                migration.main(path, check=True)
            self.assertIn('panel(s): 26', output.getvalue())
            self.assertEqual(path.read_bytes(), FIXTURE.read_bytes())
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_atomic_write_failure_leaves_original_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'appletsrc'
            path.write_bytes(FIXTURE.read_bytes())
            with patch.object(migration.os, 'replace', side_effect=OSError('injected atomic replacement failure')):
                with self.assertRaisesRegex(OSError, 'injected'):
                    migration.main(path)
            self.assertEqual(path.read_bytes(), FIXTURE.read_bytes())
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_crlf_and_unordered_quicklaunch_preserve_unrelated_bytes(self):
        original = FIXTURE.read_text().replace('127;67;28;', '127;28;').replace('\n', '\r\n')
        result, _ = migration.migrate(original)
        self.assertNotIn('plugin=org.kde.plasma.quicklaunch', result)
        self.assertIn('# This deliberately unsorted custom configuration must stay verbatim.\r\nz=last\r\n', result)
        self.assertEqual(migration.migrate(result), (result, []))

    def test_kconfig_escaped_urls_round_trip_and_deduplicate(self):
        encoded = r'applications:custom\,app.desktop,applications:custom\,app.desktop'
        self.assertEqual(normalize_launchers([encoded, 'file:///usr/share/applications/custom%2Capp.desktop']),
                         r'applications:custom\,app.desktop')
        with self.assertRaises(ValueError):
            normalize_launchers([r'applications:bad\q.desktop'])

    def test_shared_normalization_and_fresh_seed(self):
        self.assertEqual(normalize_launchers(['file:///usr/share/applications/firefox.desktop,applications:firefox.desktop',
                                             'file:///usr/local/share/applications/org.kde.dolphin.desktop,preferred://filemanager',
                                             'file:///home/tester/.local/share/applications/custom%20app.desktop',
                                             'file://remote/usr/share/applications/firefox.desktop']),
                         'applications:firefox.desktop,applications:org.win7classic.explorer.desktop,applications:custom app.desktop,file://remote/usr/share/applications/firefox.desktop')
        action = 'file:///usr/share/applications/custom.desktop?action=new-window'
        self.assertEqual(normalize_launchers([action]), action)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plasma-org.kde.plasma.desktop-appletsrc'
            path.write_text(FIXTURE.read_text().replace('plugin=org.win7classic.taskbar', 'plugin=org.kde.plasma.icontasks'))
            subprocess.run([str(ROOT / 'toggle/windows/seed'), directory], check=True, capture_output=True)
            result = path.read_text()
            self.assertNotIn('plugin=org.kde.plasma.quicklaunch', result)
            self.assertIn('launchers=' + MERGED, result)


if __name__ == '__main__':
    unittest.main()
