import QtQuick
import QtQuick.Templates as T

T.Button {
    id: button
    property string artwork: "button"
    property string fallbackLabel: text
    readonly property bool sliced: artwork !== "submit"
    implicitWidth: Math.max(108, label.implicitWidth + 30)
    implicitHeight: 28
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.65
    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    background: Item {
        Rectangle {
            anchors.fill: parent
            radius: button.sliced ? 3 : 15
            color: button.down ? "#122c49" : "#204e7b"
            border.color: "#c0daf2"
            visible: art.status !== BorderImage.Ready
        }
        BorderImage {
            id: art
            anchors.fill: parent
            source: "art/" + button.artwork + (button.down ? "-down.png" : ".png")
            border.left: button.sliced ? 9 : 0
            border.right: border.left
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            radius: button.sliced ? 2 : 13
            color: "transparent"
            border.color: "white"
            visible: button.activeFocus
        }
    }
    contentItem: Item {
        Image {
            id: glyph
            anchors.centerIn: parent
            source: button.artwork === "power" ? "art/power-icon.png" : ""
        }
        Text {
            id: label
            anchors.centerIn: parent
            text: button.fallbackLabel
            visible: button.artwork === "button" || (button.artwork === "power" ? glyph.status !== Image.Ready
                                                                              : art.status !== BorderImage.Ready)
            color: "white"
            font.pixelSize: 13
            style: Text.Outline; styleColor: "#23354b"
        }
    }
}
