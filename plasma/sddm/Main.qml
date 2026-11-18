import QtQuick
import QtQuick.Templates as T

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
    onSelectedChanged: {
        if (selected >= 0) logon.clear();
        else if (choices.itemAt(0)) choices.itemAt(0).forceActiveFocus();
    }
    Component.onCompleted: if (selected < 0 && choices.itemAt(0)) choices.itemAt(0).forceActiveFocus()

    // User tiles, when there is more than one account.
    Row {
        anchors.centerIn: parent
        visible: root.selected < 0
        spacing: 40
        Repeater {
            id: choices
            model: userModel
            delegate: T.Button {
                id: choice
                required property int index
                required property string realName
                required property string name
                width: 96; height: 118
                focusPolicy: Qt.StrongFocus
                text: realName || name
                Accessible.name: text
                onClicked: root.selected = index
                Keys.onReturnPressed: clicked()
                Keys.onEnterPressed: clicked()
                contentItem: Item {
                    // The chooser has always used smaller tiles than the selected account view.
                    LogonTile {
                        scale: 96 / 156
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: -42
                        userName: choice.text
                        userImage: root.userAt(choice.index, root.iconRole)
                    }
                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        text: choice.text
                        color: "white"; font.pixelSize: 14
                        style: Text.Outline; styleColor: "#193855"
                    }
                }
                background: Rectangle {
                    color: "transparent"; border.color: "white"; radius: 3
                    visible: choice.activeFocus
                }
            }
        }
    }

    // Keep the existing direct power action; the Windows split menu has no delegate here.
    LogonButton {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.rightMargin: 35; anchors.bottomMargin: 34
        width: 57; height: 28
        visible: sddm.canPowerOff
        artwork: "power"
        text: qsTr("Shut down")
        fallbackLabel: "⏻"
        onClicked: sddm.powerOff()
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            logon.busy = false;
            logon.showError("The user name or password is incorrect.");
        }
    }
}
