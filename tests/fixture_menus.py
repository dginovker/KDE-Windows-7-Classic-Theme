#!/usr/bin/env python3
"""Real QMenus with the action/state layout of the genuine Organize capture (#18)."""
import json
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

class Menu(QtWidgets.QMenu):
    def shortcut_box(self, action):
        option = QtWidgets.QStyleOptionMenuItem()
        self.initStyleOption(option, action)
        r = self.actionGeometry(action)
        return [r.right() - option.reservedShortcutWidth - 11, r.y(), r.right() - 11, r.y() + r.height()]


app = QtWidgets.QApplication([])
window = QtWidgets.QWidget()
window.setWindowTitle('Classic menu fixture')
window.resize(760, 533)
button = QtWidgets.QPushButton('Organize', window)
button.setGeometry(3, 37, 80, 30)
menu = QtWidgets.QMenu(window)
# Wine Tahoma advances differ; fix only the outer width for like-for-like raster comparisons.
menu.setFixedWidth(168)
pixmap = QtGui.QPixmap(16, 16)
pixmap.fill(QtCore.Qt.transparent)
icon = QtGui.QIcon(pixmap)
for label, enabled, has_icon in [
    ('Cut', False, True), ('Copy', False, True), ('Paste', False, True),
    ('Undo', False, False), ('Redo', False, False), ('', True, False),
    ('Select all', True, False), ('', True, False), ('Layout', True, True),
    ('Folder and search options', True, False), ('', True, False),
    ('Delete', False, True), ('Rename', False, False), ('Remove properties', False, False),
    ('Properties', True, False), ('', True, False), ('Close', True, False),
]:
    if not label:
        menu.addSeparator()
        continue
    if label == 'Layout':
        sub = Menu(label, menu)
        sub.setIcon(icon)
        menu.addMenu(sub)
        font = sub.font()
        font.setStyleStrategy(QtGui.QFont.NoAntialias)
        sub.setFont(font)
        group = QtGui.QActionGroup(sub)
        group.setExclusive(True)
        for name in ('Icons', 'Details'):
            action = sub.addAction(name)
            action.setCheckable(True)
            group.addAction(action)
            action.setChecked(name == 'Icons')
        checked = sub.addAction('Preview pane\tCtrl+P')
        checked.setCheckable(True)
        checked.setChecked(True)
        disabled = sub.addAction('Disabled\tCtrl+D')
        disabled.setEnabled(False)
        def submenu_report():
            sub.grab().save('/tmp/fixture-submenu.png')
            Path('/tmp/fixture-submenu.json').write_text(json.dumps({'shortcutBox': sub.shortcut_box(disabled)}))
        sub.aboutToShow.connect(lambda: QtCore.QTimer.singleShot(150, submenu_report))
        continue
    action = menu.addAction(icon, label) if has_icon else menu.addAction(label)
    action.setEnabled(enabled)
    if label == 'Close':
        action.triggered.connect(lambda: Path('/tmp/fixture-menu-triggered').write_text('Close'))


def opened():
    QtCore.QTimer.singleShot(100, lambda: Path('/tmp/fixture-menu.json').write_text(json.dumps({
        'style': app.style().name(),
        'actions': {a.text(): [menu.actionGeometry(a).x(), menu.actionGeometry(a).y(),
                              menu.actionGeometry(a).width(), menu.actionGeometry(a).height()]
                    for a in menu.actions() if not a.isSeparator()},
        'size': [menu.width(), menu.height()],
    })))


menu.aboutToShow.connect(opened)
button.clicked.connect(lambda: menu.popup(window.mapToGlobal(QtCore.QPoint(3, 64))))
view_button = QtWidgets.QPushButton('View', window)
view_button.setGeometry(90, 37, 80, 30)
view = QtWidgets.QMenu(window)
view.setFixedWidth(153)
view_group = QtGui.QActionGroup(view)
for label in ('Large icons', 'Medium icons', 'Small icons', '', 'Auto arrange icons',
              'Align icons to grid', '', 'Show desktop icons', 'Show desktop gadgets'):
    if not label:
        view.addSeparator()
        continue
    action = view.addAction(label)
    action.setCheckable(True)
    if label in ('Large icons', 'Medium icons', 'Small icons'):
        view_group.addAction(action)
    action.setChecked(label in ('Medium icons', 'Align icons to grid', 'Show desktop icons', 'Show desktop gadgets'))
view_button.clicked.connect(lambda: view.popup(window.mapToGlobal(QtCore.QPoint(90, 64))))
report = QtCore.QTimer(interval=150)
report.timeout.connect(lambda: view.grab().save('/tmp/fixture-view.png') if view.isVisible() else None)
report.start()
window.show()
app.exec()
