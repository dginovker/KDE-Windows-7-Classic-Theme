import unittest
from migrate import transform

PANEL = '''[Containments][2]
plugin=org.kde.panel
[Containments][2][General]
AppletOrder=5;6;7;8
[Containments][2][Applets][5]
plugin=org.win7classic.taskbar
[Containments][2][Applets][5][Configuration][General]
pinned=applications:dolphin.desktop,applications:kate.desktop
[Containments][2][Applets][6]
plugin=org.win7classic.trayframe
[Containments][2][Applets][7]
plugin=org.kde.plasma.systemtray
[Containments][2][Applets][7][Configuration][General]
extraItems=org.kde.plasma.volume,org.kde.plasma.battery,org.example.tray
knownItems=org.kde.plasma.volume,org.kde.plasma.battery,org.example.tray
reverseIconOrder=true
iconSpacing=1
showAllItems=false
hiddenItems=org.kde.plasma.battery,org.example.historical-sni-id
shownItems=org.kde.plasma.volume
pin=true
disabledStatusNotifiers=org.example.disabled
[Containments][2][Applets][7][Applets][31]
plugin=org.example.tray
[Containments][2][Applets][7][Applets][31][Configuration][General]
opaque=a,,b\\,c
[Containments][2][Applets][7][Shortcuts]
global=Meta+Y
[Containments][2][Applets][8]
plugin=org.example.custom-panel-widget
[Containments][2][Applets][9]
plugin=org.kde.plasma.systemtray
'''


class Migration(unittest.TestCase):
    def test_exact_bytes(self):
        for initial in (PANEL, PANEL.replace('\n', '\r\n')):
            with self.subTest(crlf='\r\n' in initial):
                result = transform(initial)
                self.assertEqual(result, initial.replace('plugin=org.kde.plasma.systemtray', 'plugin=org.win7classic.tray', 1))
                self.assertEqual(transform(result), result)
                self.assertEqual(transform(result, undo=True), initial)

    def test_ignore_current_and_unrelated(self):
        current = PANEL.replace('plugin=org.win7classic.trayframe', 'plugin=org.kde.plasma.panelspacer')
        self.assertEqual(transform(current), current)

    def test_legacy_fail_loud(self):
        legacy = PANEL + '[Containments][2][Applets][7][Configuration]\nSystrayContainmentId=23\n'
        with self.assertRaisesRegex(ValueError, 'Legacy separate tray containment'):
            transform(legacy)


if __name__ == '__main__':
    unittest.main()
