#!/usr/bin/env python3
"""Exercise the installed shutdown popup's state matrix without executing session actions."""
import json
from pathlib import Path
from PySide6 import QtCore, QtGui, QtQml

CONTROL = Path('/tmp/shutdown-fixture-control.json')
REPORT = Path('/tmp/shutdown-fixture-report.json')
app = QtGui.QGuiApplication([])
engine = QtQml.QQmlApplicationEngine()
ui = Path.home() / '.local/share/plasma/plasmoids/org.win7classic.taskbar/contents/ui'
engine.loadData(f'''
import QtQuick
import "file://{ui}" as Taskbar
Window {{
    id: root
    title: "Shutdown menu fixture"
    visible: true
    width: 14; height: 23
    flags: Qt.FramelessWindowHint
    property var capabilities: ({{}})
    property bool ready: false
    property bool switchUserSupported: true
    property int chosen: -1
    Item {{ id: anchor; width: 14; height: 23 }}
    Taskbar.ShutdownMenu {{
        objectName: "popup"
        anchor: anchor
        session: root.capabilities
        ready: root.ready
        switchUserSupported: root.switchUserSupported
        onChosen: index => root.chosen = index
    }}
}}
'''.encode())
assert engine.rootObjects(), 'shutdown fixture QML failed to load'
root = engine.rootObjects()[0]
popup = root.findChild(QtCore.QObject, 'popup')
last = None


def poll():
    global last
    text = CONTROL.read_text()
    if text != last:
        data = json.loads(text)
        last = text
        root.setProperty('capabilities', data['capabilities'])
        root.setProperty('ready', data['ready'])
        root.setProperty('switchUserSupported', data.get('switchUserSupported', True))
        root.setProperty('chosen', -1)
        if data.get('open'):
            QtCore.QMetaObject.invokeMethod(popup, 'open')
    REPORT.write_text(json.dumps({
        'current': popup.property('current'), 'visible': popup.property('visible'),
        'chosen': root.property('chosen'),
    }))


timer = QtCore.QTimer(interval=100)
timer.timeout.connect(poll)
timer.start()
app.exec()
