pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Templates as T
import QtQuick.Controls.Basic as Controls
import org.kde.plasma.workspace.keyboardlayout as Keyboards

// Windows 7 logon screen for SDDM. One user goes straight to the password; several are shown as tiles first.
Item {
    id: root
    width: 1280
    height: 800
    property int selected: userModel.count === 1 ? 0 : -1
    readonly property bool canUsePassword: selected >= 0 && !logon.busy && logon.error === ""
    readonly property bool x11KeyboardAvailable: x11Keyboard.item?.available ?? false
    readonly property bool waylandKeyboardAvailable: Qt.platform.pluginName.startsWith("wayland") && Keyboards.KWinVirtualKeyboard.available
    onCanUsePasswordChanged: {
        if (!canUsePassword && x11Keyboard?.visible)
            InputMethod.hide();
        if (!canUsePassword && waylandKeyboardAvailable && Keyboards.KWinVirtualKeyboard.visible)
            Keyboards.KWinVirtualKeyboard.active = false;
    }

    Timer {
        id: x11CapabilityCheck
        // Wait for the first password focus to reach the greeter's platform input context.
        running: x11Keyboard.active && logon.passwordFocused && !root.x11KeyboardAvailable && !warned
        interval: 1000
        property bool warned: false
        onTriggered: {
            warned = true;
            console.warn("win7-classic: X11 virtual keyboard unavailable; set [General] InputMethod=qtvirtualkeyboard in /etc/sddm.conf.d/win7-classic.conf");
        }
    }

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
        keyboardHeight: x11Keyboard.visible ? x11Keyboard.height : 0
        // TextInput otherwise asks Qt to show the keyboard when popup focus returns.
        passwordFocusOnPress: !powerMenu.restorePasswordFocus
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

    Loader {
        id: x11Keyboard
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        width: Math.min(parent.width, parent.height)
        active: Qt.platform.pluginName === "xcb"
        visible: status === Loader.Ready && item.active
        source: "GreeterKeyboard.qml"
        onStatusChanged: if (status === Loader.Error)
            console.error("win7-classic: SDDM X11 virtual keyboard requires Qt Quick Virtual Keyboard")
    }

    LogonButton {
        id: keyboardButton
        anchors.left: parent.left; anchors.bottom: parent.bottom
        anchors.leftMargin: 34; anchors.bottomMargin: 34
        width: 38; height: 28
        focusPolicy: Qt.TabFocus
        readonly property bool keyboardVisible: root.waylandKeyboardAvailable ? Keyboards.KWinVirtualKeyboard.visible : x11Keyboard.visible
        visible: !artworkFailed && root.canUsePassword && (root.waylandKeyboardAvailable || root.x11KeyboardAvailable)
        text: keyboardVisible ? qsTr("Hide Virtual Keyboard") : qsTr("Show Virtual Keyboard")
        artwork: "accessibility"
        staticArtwork: true
        z: 1
        onClicked: {
            const wasVisible = keyboardVisible;
            logon.focusPassword();
            if (root.waylandKeyboardAvailable) {
                if (wasVisible)
                    Keyboards.KWinVirtualKeyboard.active = false;
                else
                    Keyboards.KWinVirtualKeyboard.forceActivate();
            } else if (wasVisible) {
                InputMethod.hide();
            } else {
                InputMethod.show();
            }
        }
    }

    Row {
        id: power
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.rightMargin: 34; anchors.bottomMargin: 34
        visible: !x11Keyboard.visible && !(root.waylandKeyboardAvailable && Keyboards.KWinVirtualKeyboard.visible)
        readonly property bool hasMenu: sddm.canReboot || sddm.canSuspend || sddm.canHibernate

        LogonButton {
            width: 38; height: 28
            visible: sddm.canPowerOff && !artworkFailed
            artwork: "power-main"
            staticArtwork: true
            text: qsTr("Shut down")
            onClicked: if (sddm.canPowerOff) sddm.powerOff()
        }
        LogonButton {
            id: powerArrow
            width: 20; height: 28
            visible: power.hasMenu && !artworkFailed
            artwork: "power-menu"
            staticArtwork: true
            text: qsTr("Power options")
            // Pointer activation must not steal password focus before the menu can remember it.
            focusPolicy: Qt.TabFocus
            onClicked: if (power.hasMenu) powerMenu.open()
        }
        Controls.Menu {
            id: powerMenu
            x: power.width - width
            y: -height
            focus: true
            property bool restorePasswordFocus: false
            onAboutToShow: restorePasswordFocus = logon.passwordFocused
            onClosed: {
                if (restorePasswordFocus && root.canUsePassword)
                    logon.focusPassword();
                restorePasswordFocus = false;
            }
            width: Math.max(148, implicitContentWidth + leftPadding + rightPadding)
            Controls.MenuItem {
                text: qsTr("Restart")
                enabled: sddm.canReboot
                onTriggered: if (sddm.canReboot) sddm.reboot()
            }
            Controls.MenuItem {
                text: qsTr("Sleep")
                enabled: sddm.canSuspend
                onTriggered: if (sddm.canSuspend) sddm.suspend()
            }
            Controls.MenuItem {
                text: qsTr("Hibernate")
                enabled: sddm.canHibernate
                onTriggered: if (sddm.canHibernate) sddm.hibernate()
            }
            Controls.MenuItem {
                text: qsTr("Shut down")
                enabled: sddm.canPowerOff
                onTriggered: if (sddm.canPowerOff) sddm.powerOff()
            }
        }
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            logon.busy = false;
            logon.showError("The user name or password is incorrect.");
        }
    }
}
