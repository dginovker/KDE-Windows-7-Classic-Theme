import QtQuick

// Windows 7 logon screen for SDDM. One user goes straight to the password; several are shown as tiles first.
Item {
    id: root
    width: 1280
    height: 800
    property int selected: userModel.count === 1 ? 0 : -1

    function userAt(index, role) {
        return userModel.data(userModel.index(index, 0), role);
    }
    // SDDM's UserModel roles: NameRole = Qt.UserRole + 1, RealNameRole, HomeDirRole, IconRole, NeedsPasswordRole.
    readonly property int nameRole: Qt.UserRole + 1
    readonly property int realNameRole: Qt.UserRole + 2
    readonly property int iconRole: Qt.UserRole + 4

    LogonUi {
        id: logon
        anchors.fill: parent
        showUser: root.selected >= 0
        userName: root.selected >= 0 ? (root.userAt(root.selected, root.realNameRole) || root.userAt(root.selected, root.nameRole)) : ""
        userImage: root.selected >= 0 ? root.userAt(root.selected, root.iconRole) : ""
        showSwitchUser: userModel.count > 1
        onSubmitted: (password) => { busy = true; sddm.login(root.userAt(root.selected, root.nameRole), password, sessionModel.lastIndex); }
        onSwitchUserClicked: root.selected = -1
    }
    onSelectedChanged: if (selected >= 0) logon.clear()

    // User tiles, when there is more than one account.
    Row {
        anchors.centerIn: parent
        visible: root.selected < 0
        spacing: 40
        Repeater {
            model: userModel
            delegate: Column {
                required property int index
                required property string realName
                required property string name
                spacing: 8
                Rectangle {
                    width: 96; height: 96; radius: 6
                    color: "#bfe2f6"; border.color: "#f4fbff"; border.width: 4
                    Image { anchors.fill: parent; anchors.margins: 6; source: root.userAt(index, root.iconRole); fillMode: Image.PreserveAspectCrop }
                    MouseArea { anchors.fill: parent; onClicked: root.selected = index }
                }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: realName || name; color: "white"; font.pixelSize: 14 }
            }
        }
    }

    // Shut down, bottom right, like Windows' red power button.
    Rectangle {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.rightMargin: 35; anchors.bottomMargin: 35
        width: 57; height: 27; radius: 3
        visible: sddm.canPowerOff
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#e06a5a" }
            GradientStop { position: 1.0; color: "#a01e10" }
        }
        border.color: "#5e0d05"
        Text { anchors.centerIn: parent; text: "⏻"; color: "white"; font.pixelSize: 14 }
        MouseArea { anchors.fill: parent; onClicked: sddm.powerOff() }
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            logon.busy = false;
            logon.showError("The user name or password is incorrect.");
        }
    }
}
