import QtQuick
import QtQuick.Templates as T

T.Button {
    id: button
    property string artwork: "button"
    property string fallbackLabel: text
    property bool staticArtwork: false
    readonly property bool artworkFailed: art.status === BorderImage.Error
    readonly property bool sliced: artwork === "button"
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
            visible: !button.staticArtwork && art.status !== BorderImage.Ready
        }
        BorderImage {
            id: art
            anchors.fill: parent
            source: "art/" + button.artwork + (button.down && !button.staticArtwork ? "-down.png" : ".png")
            border.left: button.sliced ? 9 : 0
            border.right: border.left
        }
        Rectangle {
            anchors.fill: parent
            color: "black"
            opacity: 0.18
            visible: button.staticArtwork && button.down && art.status === BorderImage.Ready
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
        Text {
            id: label
            anchors.centerIn: parent
            text: button.fallbackLabel
            visible: !button.staticArtwork && (button.sliced || art.status !== BorderImage.Ready)
            color: "white"
            font.pixelSize: 13
            style: Text.Outline; styleColor: "#23354b"
        }
    }
}
