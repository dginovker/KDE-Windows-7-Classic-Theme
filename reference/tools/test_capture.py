#!/usr/bin/env python3
"""Host-only checks for capture.py's cropped comparisons and failure cleanup."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture


class CaptureTests(unittest.TestCase):
    def test_notification_area_masks_only_clock_text(self):
        with tempfile.TemporaryDirectory() as directory:
            reference, actual = [Path(directory) / name for name in ('reference.png', 'actual.png')]
            image = Image.new('RGB', (180, 44), 'white')
            image.save(reference)
            image.putpixel((120, 20), (0, 0, 0))
            image.save(actual)
            self.assertEqual(capture.differing_pixels(reference, actual, 'notification-area'), (0, None))
            for point in ((0, 0), (35, 20), (179, 43)):
                with self.subTest(point=point):
                    changed = image.copy()
                    changed.putpixel(point, (0, 0, 0))
                    changed.save(actual)
                    self.assertEqual(capture.differing_pixels(reference, actual, 'notification-area')[0], 1)

    def test_new_scenes_clean_up_when_screenshot_fails(self):
        for scene in ('explorer-file-context', 'shutdown-menu', 'desktop-view-submenu', 'explorer-view-submenu',
                      'desktop-view-checked-hover', 'explorer-view-radio-hover'):
            with self.subTest(scene=scene), \
                    patch.object(sys, 'argv', ['capture.py', scene]), \
                    patch.dict(capture.SCENES, {scene: lambda: None}), \
                    patch.object(capture.vmctl, 'start'), \
                    patch.object(capture.vmctl, 'virsh', side_effect=RuntimeError('screenshot failed')), \
                    patch.object(capture.vmctl, 'pointer') as pointer, \
                    patch.object(capture.vmctl, 'button') as button, \
                    patch.object(capture.vmctl, 'keys') as keys, \
                    patch.object(capture, 'run_dialog') as run_dialog, \
                    patch.object(capture, 'active_explorer') as active_explorer, \
                    patch.object(capture.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'screenshot failed'):
                    capture.main()
                pointer.assert_any_call(capture.VM, 640, 600)
                button.assert_called_once_with(capture.VM, 'left', False)
                self.assertEqual(keys.call_count, 1 if scene == 'explorer-file-context' else 2)
                if scene == 'explorer-file-context':
                    run_dialog.assert_called_once_with('cmd /c del "%USERPROFILE%\\Classic-demo\\capture-reference.txt"')
                    active_explorer.assert_called_once_with()
                else:
                    active_explorer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
