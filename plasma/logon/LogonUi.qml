import QtQuick

// The lock overlay and the opt-in SDDM theme carry identical local copies of the Windows 7 bitmap resources.
Item {
    id: logon
    property string userName
    property url userImage
    property string subtitle
    property bool showSwitchUser: false
    property bool showUser: true
    property bool busy: false
    property string error: ""
    property real keyboardHeight: 0
    readonly property real promptHeight: height - keyboardHeight
    readonly property alias password: field.text
    readonly property alias passwordFocused: field.activeFocus
    property alias passwordFocusOnPress: field.activeFocusOnPress
    signal submitted(string password)
    signal switchUserClicked()
    signal errorDismissed()

    function focusPassword() { field.forceActiveFocus(); }
    function clear() { field.text = ""; focusPassword(); }
    function showError(message) { error = message; okButton.forceActiveFocus(); }
    function dismissError() { error = ""; clear(); errorDismissed(); }

    // Missing decoration must never hide the controls or make white text illegible.
    Rectangle { anchors.fill: parent; color: "#0b427b" }
    Image {
        anchors.fill: parent
        source: "art/background.jpg"
        fillMode: Image.PreserveAspectCrop
    }
    Image {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 23 + logon.keyboardHeight
        width: Math.min(350, parent.width)
        height: 50
        fillMode: Image.PreserveAspectFit
        visible: status === Image.Ready && logon.promptHeight >= 420
        source: "art/branding.png"
    }

    Item {
        id: centre
        visible: logon.showUser
        width: Math.min(300, parent.width)
        anchors.horizontalCenter: parent.horizontalCenter
        readonly property bool compact: logon.promptHeight < 420
        y: Math.max(compact ? 0 : 26, Math.min(logon.promptHeight / 2 - (logon.subtitle ? 127 : 97),
                    logon.promptHeight - (compact ? 275 : 412)))

        LogonTile {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.horizontalCenterOffset: -1
            y: compactOffset - 22
            userName: logon.userName
            userImage: logon.userImage
            readonly property int compactOffset: centre.compact ? 12 : 0
        }

        component Shadowed: Item {
            property alias text: label.text
            property alias font: label.font
            width: parent.width; height: label.implicitHeight
            Text {
                id: label
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                color: "white"; style: Text.Outline; styleColor: "#193855"
            }
        }

        Shadowed { y: 170; text: logon.userName; font.pixelSize: 23 }
        Shadowed { y: 200; visible: logon.subtitle !== ""; text: logon.subtitle; font.pixelSize: 12 }

        Item {
            visible: logon.error === ""
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(259, parent.width); height: 30
            anchors.horizontalCenterOffset: width === 259 ? 17 : 0
            y: logon.subtitle ? 224 : 208
            Rectangle {
                width: parent.width - 34; height: 23
                radius: 2
                color: "white"
                border.color: field.activeFocus ? "#174c80" : "#5d7f9f"
                TextInput {
                    id: field
                    anchors.fill: parent; anchors.leftMargin: 5; anchors.rightMargin: 5
                    verticalAlignment: TextInput.AlignVCenter
                    echoMode: TextInput.Password
                    passwordCharacter: "●"
                    font.pixelSize: 12
                    enabled: !logon.busy
                    activeFocusOnTab: true
                    clip: true
                    Accessible.name: qsTr("Password")
                    onAccepted: if (text !== "") logon.submitted(text)
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: field.text === ""
                        text: qsTr("Password")
                        font: field.font
                        color: "#666666"
                    }
                }
            }
            LogonButton {
                anchors.right: parent.right
                y: -4
                width: 30; height: 30
                text: logon.subtitle ? qsTr("Unlock") : qsTr("Log in")
                artwork: "submit"
                fallbackLabel: "→"
                enabled: !logon.busy
                onClicked: if (field.text !== "") logon.submitted(field.text)
            }
        }

        Column {
            visible: logon.error !== ""
            y: 216; width: parent.width
            spacing: 12
            Shadowed { text: logon.error; font.pixelSize: 13 }
            LogonButton {
                id: okButton
                anchors.horizontalCenter: parent.horizontalCenter
                text: qsTr("OK")
                onClicked: logon.dismissError()
            }
        }

        LogonButton {
            visible: logon.showSwitchUser && logon.error === ""
            anchors.horizontalCenter: parent.horizontalCenter
            y: centre.compact ? 242 : 307
            text: qsTr("Switch User")
            onClicked: logon.switchUserClicked()
        }
    }

    Component.onCompleted: if (showUser) focusPassword()
}
