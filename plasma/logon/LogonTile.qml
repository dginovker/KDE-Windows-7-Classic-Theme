import QtQuick

Item {
    id: tile
    property string userName
    property url userImage
    width: 190; height: 190

    Rectangle {
        x: 31; y: 32; width: 128; height: 128
        color: "#bfe2f6"
        border.color: "#315476"
        clip: true
        Image {
            id: picture
            anchors.fill: parent
            source: tile.userImage
            fillMode: Image.PreserveAspectCrop
            sourceSize: Qt.size(256, 256)
        }
        Text {
            anchors.centerIn: parent
            visible: picture.status !== Image.Ready
            text: tile.userName.charAt(0).toUpperCase()
            font.pixelSize: 64
            color: "#315476"
        }
    }
    Image { anchors.fill: parent; source: "art/tile.png" }
}
