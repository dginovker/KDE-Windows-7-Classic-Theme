#!/usr/bin/env python3
"""Long-lived Qt/KDE platform-theme consumer for test_icons.py."""
from PySide6 import QtCore, QtGui, QtWidgets

app = QtWidgets.QApplication([])
window = QtWidgets.QLabel()
window.setWindowTitle('Live folder icon')
window.setAlignment(QtCore.Qt.AlignCenter)
window.resize(200, 160)
timer = QtCore.QTimer(interval=200)
timer.timeout.connect(lambda: window.setPixmap(QtGui.QIcon.fromTheme('folder').pixmap(48, 48)))
timer.start()
window.show()
app.exec()
