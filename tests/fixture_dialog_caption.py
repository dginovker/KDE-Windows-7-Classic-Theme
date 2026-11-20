"""Real Qt modal message box, nonmodal dialog, or XWayland What's This dialog."""
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QVBoxLayout, QWhatsThis, QWidget

app = QApplication([])
owner = QWidget()
owner.setWindowTitle('Caption probe owner')
owner.resize(440, 260)
owner.show()

kind = sys.argv[1]
if kind == 'message':
    # Keep title glyphs outside the caption-button measurement even with wider host font metrics.
    QMessageBox.information(owner, 'Modal caption probe', 'This message box exercises Classic modal caption buttons.',
                            QMessageBox.Ok | QMessageBox.Cancel)
else:
    flags = Qt.WindowType
    dialog = QDialog(owner, flags.Dialog | flags.WindowCloseButtonHint
                     | (flags.WindowContextHelpButtonHint if kind == 'help' else flags.WindowMinMaxButtonsHint))
    dialog.setWindowTitle(f'{kind} caption probe')
    layout = QVBoxLayout(dialog)
    label = QLabel('Caption probe')
    label.setWhatsThis('Live context help from the client')
    layout.addWidget(label)
    dialog.resize(300, 140)
    dialog.setModal(kind == 'help')
    dialog.show()
    timer = QTimer(interval=60)
    if kind == 'help':
        def report_help_mode():
            if QWhatsThis.inWhatsThisMode():
                Path(sys.argv[2]).touch()
                timer.stop()

        timer.timeout.connect(report_help_mode)
        timer.start()
    app.exec()
