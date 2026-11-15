import QtQuick
import QtQuick.Shapes

// The Windows 7 logon/lock screen, shared by the Plasma lock screen and the SDDM theme. Geometry is measured from
// reference/screenshots/w7-lock.png at 1280x800 and kept centred; Microsoft's background and frame bitmaps can't be
// shipped, so both are drawn.
Item {
    id: logon
    property string userName
    property url userImage
    property string subtitle           // "Locked" on the lock screen
    property bool showSwitchUser: false
    property bool showUser: true      // false: background only, for SDDM's user chooser
    property bool busy: false
    property string error: ""
    readonly property alias password: field.text
    signal submitted(string password)
    signal switchUserClicked()
    signal errorDismissed()

    readonly property string uiFont: Qt.fontFamilies().indexOf("Segoe UI") >= 0 ? "Segoe UI" : "Noto Sans"

    function clear() { field.text = ""; field.forceActiveFocus(); }
    function showError(message) { error = message; okButton.forceActiveFocus(); }
    function dismissError() { error = ""; clear(); errorDismissed(); }

    // Background: deep blue top-left to bright cyan bottom-right, like the Windows 7 logon wallpaper.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "#063a78" }
            GradientStop { position: 0.45; color: "#0b70cf" }
            GradientStop { position: 1.0; color: "#1ea1e6" }
        }
    }
    Shape {
        anchors.fill: parent
        ShapePath {
            strokeWidth: -1
            fillGradient: RadialGradient {
                centerX: logon.width * 0.86; centerY: logon.height * 0.82; centerRadius: logon.width * 0.45
                focalX: centerX; focalY: centerY
                GradientStop { position: 0.0; color: "#e0f8ff" }
                GradientStop { position: 0.35; color: "#8ad8f6" }
                GradientStop { position: 1.0; color: "#001ea1e6" }
            }
            PathRectangle { x: 0; y: 0; width: logon.width; height: logon.height }
        }
    }

    Item {
        id: centre
        visible: logon.showUser
        width: 300; height: 360
        anchors.centerIn: parent
        // Reference tile top is at y 273 of 800 when locked and 303 at logon, where there is no subtitle line.
        anchors.verticalCenterOffset: logon.subtitle !== "" ? 53 : 83

        // User tile: glassy rounded frame around the picture.
        Rectangle {
            id: tile
            x: (parent.width - 142) / 2 - 4; y: 0
            width: 142; height: 140; radius: 7
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#f4fbff" }
                GradientStop { position: 1.0; color: "#8fc2e6" }
            }
            border.color: "#4f87b5"
            Rectangle {
                x: 7; y: 7; width: parent.width - 14; height: parent.height - 14; radius: 3
                color: "#bfe2f6"
                clip: true
                Image {
                    anchors.fill: parent
                    source: logon.userImage
                    fillMode: Image.PreserveAspectCrop
                    sourceSize: Qt.size(256, 256)
                    visible: status === Image.Ready
                }
                Text {   // initials when there is no picture
                    anchors.centerIn: parent
                    visible: logon.userImage.toString() === "" || parent.children[0].status !== Image.Ready
                    text: logon.userName.charAt(0).toUpperCase()
                    font.family: logon.uiFont; font.pixelSize: 64
                    color: "#3c78aa"
                }
            }
        }

        component Shadowed: Item {
            property alias text: label.text
            property alias font: label.font
            width: parent.width; height: label.implicitHeight
            Text { x: 1; y: 1; width: parent.width; horizontalAlignment: Text.AlignHCenter; text: label.text; font: label.font; color: "#80000000" }
            Text { id: label; width: parent.width; horizontalAlignment: Text.AlignHCenter; color: "white"; renderType: Text.NativeRendering }
        }

        Shadowed { y: 170; text: logon.userName; font.family: logon.uiFont; font.pixelSize: 23 }
        Shadowed { y: 200; visible: logon.subtitle !== ""; text: logon.subtitle; font.family: logon.uiFont; font.pixelSize: 12 }

        // Password row: white field with a round "go" button to its right.
        Item {
            visible: logon.error === ""
            x: (parent.width - 225) / 2 - 2; y: logon.subtitle !== "" ? 224 : 208
            width: 260; height: 30
            Rectangle {
                width: 225; height: 23
                radius: 2
                color: "white"
                border.color: "#5d7f9f"
                TextInput {
                    id: field
                    anchors.fill: parent; anchors.leftMargin: 5; anchors.rightMargin: 5
                    verticalAlignment: TextInput.AlignVCenter
                    echoMode: TextInput.Password
                    passwordCharacter: "●"
                    font.family: logon.uiFont; font.pixelSize: 12
                    enabled: !logon.busy
                    focus: true
                    clip: true
                    onAccepted: if (text !== "") logon.submitted(text)
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: field.text === ""
                        text: "Password"
                        font: field.font
                        color: "#8a8a8a"
                    }
                }
            }
            Rectangle {   // go button
                x: 230; y: -4
                width: 30; height: 30; radius: 15
                gradient: Gradient {
                    GradientStop { position: 0.0; color: go.pressed ? "#5c9ad0" : "#d9eefb" }
                    GradientStop { position: 1.0; color: go.pressed ? "#1f5e96" : "#4a8fc8" }
                }
                border.color: "#2a5f8c"
                Shape {
                    anchors.centerIn: parent
                    width: 14; height: 12
                    ShapePath {
                        strokeColor: "transparent"; fillColor: "white"
                        startX: 0; startY: 4
                        PathLine { x: 7; y: 4 } PathLine { x: 7; y: 0 } PathLine { x: 14; y: 6 }
                        PathLine { x: 7; y: 12 } PathLine { x: 7; y: 8 } PathLine { x: 0; y: 8 } PathLine { x: 0; y: 4 }
                    }
                }
                MouseArea { id: go; anchors.fill: parent; onClicked: if (field.text !== "") logon.submitted(field.text) }
            }
        }

        // Wrong password: message and OK, as Windows shows it.
        Column {
            visible: logon.error !== ""
            y: 216; width: parent.width
            spacing: 12
            Shadowed { text: logon.error; font.family: logon.uiFont; font.pixelSize: 13 }
            GlassButton {
                id: okButton
                anchors.horizontalCenter: parent.horizontalCenter
                text: "OK"
                onClicked: logon.dismissError()
                Keys.onReturnPressed: logon.dismissError()
                Keys.onEnterPressed: logon.dismissError()
            }
        }

        GlassButton {
            visible: logon.showSwitchUser && logon.error === ""
            anchors.horizontalCenter: parent.horizontalCenter
            y: 307
            text: "Switch User"
            onClicked: logon.switchUserClicked()
        }
    }

    component GlassButton: Rectangle {
        id: button
        property string text
        signal clicked()
        width: Math.max(105, label.implicitWidth + 30); height: 27; radius: 3
        gradient: Gradient {
            GradientStop { position: 0.0; color: area.pressed ? "#1d4f7c" : "#5d95c4" }
            GradientStop { position: 0.5; color: area.pressed ? "#173f63" : "#2c6aa0" }
            GradientStop { position: 1.0; color: area.pressed ? "#2b5f8c" : "#3a7cb3" }
        }
        border.color: activeFocus ? "white" : "#1c4870"
        Text { id: label; anchors.centerIn: parent; text: button.text; color: "white"; font.family: logon.uiFont; font.pixelSize: 13 }
        MouseArea { id: area; anchors.fill: parent; onClicked: button.clicked() }
    }

    Component.onCompleted: field.forceActiveFocus()
}
