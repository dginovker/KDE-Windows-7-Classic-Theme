import QtQuick

// Windows mode's lock screen. kscreenlocker_greet loads this from the shell package's lockscreen/ folder and
// provides `authenticator`, `kscreenlocker_userName` and `kscreenlocker_userImage`.
// This file deliberately uses only QtQuick: kscreenlocker's own fallback (used when this file fails to load) never
// starts PAM in Plasma 6.8, so it can't unlock. The Windows UI is therefore loaded separately, and if it fails a
// plain password field from this file takes over, which can always unlock.
Item {
    id: root
    // Properties and signals kscreenlocker looks for on the root item.
    property bool debug: false
    property string notification
    property bool viewVisible: false
    signal clearPassword()
    signal notificationRepeated()

    implicitWidth: 800
    implicitHeight: 600

    readonly property bool plain: ui.status === Loader.Error
    property bool busy: false

    function submit(password) {
        busy = true;
        authenticator.respond(password);
    }

    Loader {
        id: ui
        anchors.fill: parent
        source: "LogonUi.qml"
        onStatusChanged: if (status === Loader.Error)
            console.error("win7-classic: Windows lock screen failed to load; showing the plain password field instead");
        onLoaded: {
            item.userName = kscreenlocker_userName;
            item.userImage = kscreenlocker_userImage !== "" ? "file://" + kscreenlocker_userImage : "";
            item.subtitle = "Locked";
            item.submitted.connect(root.submit);
            item.errorDismissed.connect(() => authenticator.startAuthenticating());
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: root.plain
        color: "#0b4f9c"
        Column {
            anchors.centerIn: parent
            spacing: 10
            Text { text: kscreenlocker_userName + " — Locked"; color: "white"; font.pixelSize: 20 }
            Text { id: plainError; color: "white"; font.pixelSize: 13 }
            Rectangle {
                width: 260; height: 28; color: "white"
                TextInput {
                    id: plainField
                    anchors.fill: parent; anchors.margins: 6
                    echoMode: TextInput.Password
                    focus: root.plain
                    enabled: !root.busy
                    onAccepted: { plainError.text = ""; root.submit(text); }
                }
            }
        }
    }

    Connections {
        target: root
        function onClearPassword() { root.plain ? plainField.clear() : ui.item.clear(); }
    }
    Connections {
        target: authenticator
        function onSucceeded() {
            authenticator.stopAuthenticating();
            Qt.quit();
        }
        function onFailed(kind) {
            // Non-zero kinds are fingerprint/smartcard attempts in the background; only report password failures.
            if (kind !== 0)
                return;
            root.busy = false;
            const message = "The user name or password is incorrect.";
            if (root.plain) {
                plainError.text = message;
                plainField.clear();
                authenticator.startAuthenticating();
            } else {
                ui.item.busy = false;
                ui.item.showError(message);
            }
        }
    }

    // Keep PAM ready for a password, as Plasma's own lock screen does.
    Timer {
        interval: 1000; running: true; repeat: true; triggeredOnStart: true
        onTriggered: authenticator.startAuthenticating()
    }
}
