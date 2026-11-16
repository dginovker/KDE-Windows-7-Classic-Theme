#!/usr/bin/env python3
"""Qt window used by test_frames.py: titled like the Windows fixture, with the native-bench control layout.

Control positions match reference/tools/native-bench.c, so its client area lines up with
reference/screenshots/controls-native-client.png when the window's frame matches Windows'.
Style, palette and fonts come from the desktop (kdeglobals), not from this script.
"""
import sys
import json
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

app = QtWidgets.QApplication([])
window = QtWidgets.QDialog() if '--dialog' in sys.argv else QtWidgets.QWidget()
window.setWindowTitle('Classic-demo')


def place(widget, x, y, w, h):
    widget.setParent(window)
    widget.setGeometry(x, y, w, h)
    return widget


place(QtWidgets.QLabel('Qt controls; desktop style, palette and font'), 24, 20, 800, 24)
place(QtWidgets.QPushButton('Normal'), 24, 65, 130, 26)
place(QtWidgets.QPushButton('Pressed'), 174, 65, 130, 26).setDown(True)
place(QtWidgets.QPushButton('Disabled'), 324, 65, 130, 26).setEnabled(False)
focused = place(QtWidgets.QPushButton('Focused'), 474, 65, 130, 26)
focused.setAutoDefault(False)
default = place(QtWidgets.QPushButton('Default'), 624, 65, 130, 26)
default.setDefault(True)
place(QtWidgets.QCheckBox('Unchecked'), 24, 120, 150, 24)
place(QtWidgets.QCheckBox('Checked'), 190, 120, 150, 24).setChecked(True)
off = place(QtWidgets.QCheckBox('Disabled checked'), 356, 120, 190, 24)
off.setChecked(True)
off.setEnabled(False)
place(QtWidgets.QRadioButton('Radio'), 24, 162, 150, 24)
place(QtWidgets.QRadioButton('Selected radio'), 190, 162, 180, 24).setChecked(True)
place(QtWidgets.QLineEdit('Editable text'), 24, 215, 280, 24).setProperty('classicFlatBorder', True)
disabled_edit = place(QtWidgets.QLineEdit('Disabled text'), 324, 215, 280, 24)
disabled_edit.setProperty('classicFlatBorder', True)
disabled_edit.setEnabled(False)
place(QtWidgets.QLineEdit('Sunken client edge'), 624, 215, 280, 24)
combo = place(QtWidgets.QComboBox(), 24, 265, 280, 24)
combo.addItems(['Selected option', 'Another option'])
combo.setFixedHeight(combo.sizeHint().height())
scroll = place(QtWidgets.QScrollBar(QtCore.Qt.Horizontal), 324, 265, 280, 17)
scroll.setRange(0, 100)
scroll.setPageStep(0)
place(QtWidgets.QGroupBox('Group box'), 24, 330, 580, 120)
place(QtWidgets.QLabel('The reference is rendered by Windows, not a web simulator.'), 44, 368, 540, 24)
# Report the app font so the test can see whether switching modes reaches already-running apps.
report = QtCore.QTimer(interval=300)
def report_palette():
    roles = [name for name in QtGui.QPalette.ColorRole.__members__ if name not in ('NoRole', 'NColorRoles')]
    groups = ('Active', 'Inactive', 'Disabled')
    result = {'style': app.style().name()}
    for name, widget in [('app', app), ('combo', combo), ('scroll', scroll), ('group', window.findChild(QtWidgets.QGroupBox))]:
        result[name] = {g: {r: widget.palette().color(getattr(QtGui.QPalette, g), getattr(QtGui.QPalette, r)).name()
                           for r in roles} for g in groups}
    Path('/tmp/fixture-palette.new').write_text(json.dumps(result))
    Path('/tmp/fixture-palette.new').replace('/tmp/fixture-palette.json')
report.timeout.connect(report_palette)
report.timeout.connect(lambda: combo.setFixedHeight(combo.sizeHint().height()))
report.timeout.connect(lambda: open('/tmp/fixture-font.txt', 'w').write(
    f'{QtGui.QFontInfo(app.font()).family()} {QtGui.QFontInfo(app.font()).pixelSize()}\n'))
report.start()
window.resize(992, 533)
window.show()
window.setAttribute(QtCore.Qt.WA_KeyboardFocusChange, True)
focused.setFocus(QtCore.Qt.TabFocusReason)
app.exec()
