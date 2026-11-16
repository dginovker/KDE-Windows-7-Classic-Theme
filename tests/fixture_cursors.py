#!/usr/bin/env python3
"""White/dark text fields and animation shapes for test_cursors.py."""
from PySide6 import QtCore, QtWidgets

app = QtWidgets.QApplication([])
window = QtWidgets.QWidget()
window.setWindowTitle('Live cursor fields')
window.resize(700, 300)
for x, color in ((20, 'white'), (370, 'black')):
    field = QtWidgets.QLineEdit(window)
    field.setGeometry(x, 40, 300, 100)
    field.setStyleSheet(f'background:{color}; border:0;')
for x, shape in ((20, QtCore.Qt.WaitCursor), (370, QtCore.Qt.BusyCursor)):
    label = QtWidgets.QLabel('Animated cursor', window)
    label.setGeometry(x, 180, 300, 100)
    label.setCursor(shape)
window.show()
app.exec()
