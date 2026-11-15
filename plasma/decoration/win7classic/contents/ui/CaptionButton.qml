import QtQuick
import org.kde.kwin.decoration

// DrawFrameControl caption button: 16x14 bevel, sunken with the glyph shifted 1px while pressed.
// Glyph rectangles are measured from reference/screenshots/w7-{taskbar,maximized}.png.
// Not a DecorationButton: KWin sends no moves while a button is held, so MouseArea's clicked fires even when the
// pointer is released elsewhere. Windows cancels the action in that case, so the release position is checked here.
Item {
    id: button
    required property int buttonType
    width: 16
    height: 14
    enabled: buttonType === DecorationOptions.DecorationButtonClose ? decoration.client.closeable
        : buttonType === DecorationOptions.DecorationButtonMinimize ? decoration.client.minimizeable
        : decoration.client.maximizeable
    readonly property bool sunken: mouse.pressed
    readonly property var glyph: {
        switch (buttonType) {
        case DecorationOptions.DecorationButtonMinimize:
            return [[4, 9, 6, 2]];
        case DecorationOptions.DecorationButtonMaximizeRestore:
            return decoration.client.maximized
                ? [[5, 2, 6, 2], [5, 4, 1, 1], [10, 4, 1, 4], [3, 5, 6, 2], [3, 7, 1, 4], [8, 7, 3, 1], [8, 8, 1, 2], [3, 10, 6, 1]]
                : [[3, 2, 9, 2], [3, 4, 1, 6], [11, 4, 1, 6], [3, 10, 9, 1]];
        case DecorationOptions.DecorationButtonClose:
            return [[4, 3, 2, 1], [10, 3, 2, 1], [5, 4, 2, 1], [9, 4, 2, 1], [6, 5, 4, 1], [7, 6, 2, 1],
                    [6, 7, 4, 1], [5, 8, 2, 1], [9, 8, 2, 1], [4, 9, 2, 1], [10, 9, 2, 1]];
        default:
            return [];
        }
    }

    Rectangle { anchors.fill: parent; color: "#d4d0c8" }
    Rectangle { x: 0; y: 0; width: 15; height: 1; color: button.sunken ? "#404040" : "#ffffff" }
    Rectangle { x: 0; y: 0; width: 1; height: 13; color: button.sunken ? "#404040" : "#ffffff" }
    Rectangle { x: 1; y: 1; width: 13; height: 1; color: "#808080"; visible: button.sunken }
    Rectangle { x: 1; y: 1; width: 1; height: 11; color: "#808080"; visible: button.sunken }
    Rectangle { x: 14; y: 1; width: 1; height: 12; color: "#808080"; visible: !button.sunken }
    Rectangle { x: 1; y: 12; width: 14; height: 1; color: "#808080"; visible: !button.sunken }
    Rectangle { x: 15; y: 0; width: 1; height: 14; color: button.sunken ? "#ffffff" : "#404040" }
    Rectangle { x: 0; y: 13; width: 16; height: 1; color: button.sunken ? "#ffffff" : "#404040" }

    MouseArea {
        id: mouse
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
        onReleased: (event) => {
            if (event.x < 0 || event.y < 0 || event.x >= width || event.y >= height)
                return;
            if (button.buttonType === DecorationOptions.DecorationButtonClose)
                decoration.requestClose();
            else if (button.buttonType === DecorationOptions.DecorationButtonMinimize)
                decoration.requestMinimize();
            else
                decoration.requestToggleMaximization(event.button);
        }
    }
    Repeater {
        model: button.glyph
        delegate: Rectangle {
            required property var modelData
            readonly property int shift: button.sunken ? 1 : 0
            x: modelData[0] + shift; y: modelData[1] + shift
            width: modelData[2]; height: modelData[3]
            color: button.enabled ? "#000000" : "#808080"
        }
    }
}
