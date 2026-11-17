#!/usr/bin/env python3
"""Only the project's legacy Aurorae identity is migrated, including saved current mode."""
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
import io
import json
from pathlib import Path
import tempfile
import unittest

keys = SourceFileLoader('kconfig_keys', str(Path(__file__).resolve().parents[1] / 'toggle/kconfig-keys')).load_module()
GROUP = '[org.kde.kdecoration2]'


class DecorationMigrationTests(unittest.TestCase):
    def test_live_and_saved_current_identity_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, state = root / 'config', root / 'state'
            config.mkdir()
            original = '# Keep this comment\n[Unrelated]\nvalue=win7classic\n' + GROUP + '\nButtonsOnRight=X\nlibrary=org.kde.kwin.aurorae\ntheme=win7classic\n'
            (config / 'kwinrc').write_text(original)
            current = state / 'profiles/current/keys.json'
            current.parent.mkdir(parents=True)
            data = {'kwinrc': {GROUP: {'library': 'org.kde.kwin.aurorae', 'theme': 'win7classic', 'ButtonsOnRight': 'X'}},
                    'untouched': {'theme': 'win7classic'}}
            current.write_text(json.dumps(data, indent=1, sort_keys=True) + '\n')
            windows = state / 'profiles/windows/keys.json'
            windows.parent.mkdir()
            windows.write_text(current.read_text())
            old_windows = windows.read_bytes()
            with redirect_stdout(io.StringIO()):
                keys.migrate_decoration(config, state)
            self.assertEqual((config / 'kwinrc').read_text(), original.replace('theme=win7classic\n', 'theme=win7classic2\n'))
            data['kwinrc'][GROUP]['theme'] = 'win7classic2'
            self.assertEqual(json.loads(current.read_text()), data)
            self.assertEqual(windows.read_bytes(), old_windows)
            before = (config / 'kwinrc').read_bytes(), current.read_bytes()
            with redirect_stdout(io.StringIO()) as output:
                keys.migrate_decoration(config, state)
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(before, ((config / 'kwinrc').read_bytes(), current.read_bytes()))

    def test_other_library_is_not_our_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = GROUP + '\nlibrary=other\ntheme=win7classic\n'
            (root / 'kwinrc').write_text(original)
            keys.migrate_decoration(root, root / 'state')
            self.assertEqual((root / 'kwinrc').read_text(), original)


if __name__ == '__main__':
    unittest.main()
