"""Guest-side real QMenus for test_menu_shadow_ownership.py."""
import os
from pathlib import Path
import sys

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QStyleFactory, QWidget


def mark(text):
    print(f'PROBE {text}', file=sys.stderr, flush=True)


class WhiteWindow(QWidget):
    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), QColor('white'))


app = QApplication([])
assert app.platformName() == 'wayland'
app.setStyle('Win7Classic')
assert app.style().name().lower() == 'win7classic'
window = WhiteWindow()
window.setWindowTitle('Menu shadow ownership fixture')
window.resize(560, 430)
foreign = QWidget(window)
foreign.setGeometry(10, 10, 155, 50)
fusion = QStyleFactory.create('Fusion')
assert fusion and fusion.name().lower() == 'fusion'
foreign.setStyle(fusion)
foreign.setStyleSheet('QMenu { background: #e6f0fa; border: 2px solid #124b67; }')
negative = QMenu(foreign)
positive = QMenu(window)


def setup(menu, parent, label, x):
    menu.addAction('First item')
    menu.addAction('Second item')
    menu.setFixedWidth(168)
    button = QPushButton(label, parent)
    button.setGeometry(x, 5, 135, 35)

    def show():
        if menu is negative:
            assert foreign.testAttribute(Qt.WidgetAttribute.WA_SetStyle)
            assert not menu.testAttribute(Qt.WidgetAttribute.WA_SetStyle)
            assert not menu.styleSheet() and foreign.styleSheet()
            assert menu.style() == foreign.style() and menu.style() != app.style() and menu.style() != fusion
            mark('inherited WA_SetStyle=false parent_explicit=Fusion shares_parent_wrapper=true effective_is_Classic=false')
        else:
            assert menu.style() == app.style()
            mark(f'direct {app.style().name().lower()}')
        menu.popup(button.mapToGlobal(QPoint(0, button.height())))

    button.pressed.connect(show)
    menu.aboutToHide.connect(lambda: mark('hide ' + label))
    return button


buttons = (setup(negative, foreign, 'Inherited', 0), setup(positive, window, 'Direct', 205))
switch = Path(sys.argv[1])


def switch_style():
    if switch.exists():
        switch.unlink()
        assert positive.isVisible() and positive.style() == app.style()
        mark('switch Classic to Fusion with popup visible')
        app.setStyle('Fusion')
        mark(f'switched {app.style().name().lower()} pid={os.getpid()}')


timer = QTimer(interval=100)
timer.timeout.connect(switch_style)
timer.start()
window.show()
mark(f'ready pid={os.getpid()}')
app.exec()
