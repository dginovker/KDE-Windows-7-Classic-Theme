import QtQuick
import QtQuick.Window
import org.kde.plasma.core as PlasmaCore

PlasmaCore.Dialog {
    id: tooltip
    required property Item button
    property string text
    property point pointer
    type: PlasmaCore.Dialog.Tooltip
    flags: Qt.ToolTip | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint
    backgroundHints: PlasmaCore.Dialog.NoBackground
    location: PlasmaCore.Types.Floating
    x: Math.min(button.mapToGlobal(pointer.x, 0).x, button.Screen.virtualX + button.Screen.width - body.width)
    y: button.mapToGlobal(0, pointer.y).y + 21 + body.height <= button.Screen.virtualY + button.Screen.height
       ? button.mapToGlobal(0, pointer.y).y + 21 : button.mapToGlobal(0, 0).y - body.height - 3

    mainItem: Rectangle {
        id: body
        width: Math.ceil(label.implicitWidth) + 6
        height: 16
        color: "#ffffe1"
        border.color: "black"
        Text {
            id: label
            x: 3; height: parent.height
            verticalAlignment: Text.AlignVCenter
            text: tooltip.text
            font.family: "Tahoma"; font.pixelSize: 11
            color: "black"
            renderType: Text.NativeRendering
        }
    }
}
