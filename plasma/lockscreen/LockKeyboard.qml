import QtQuick
import org.kde.plasma.workspace.keyboardlayout as Keyboards

LogonButton {
    property var focusPassword
    width: 38; height: 28
    focusPolicy: Qt.TabFocus
    visible: Keyboards.KWinVirtualKeyboard.available && !artworkFailed
    text: Keyboards.KWinVirtualKeyboard.visible ? qsTr("Hide Virtual Keyboard") : qsTr("Show Virtual Keyboard")
    artwork: "accessibility"
    staticArtwork: true
    function hide() {
        if (Keyboards.KWinVirtualKeyboard.visible)
            Keyboards.KWinVirtualKeyboard.active = false;
    }
    onClicked: {
        if (Keyboards.KWinVirtualKeyboard.visible) {
            hide();
            focusPassword();
        } else {
            focusPassword();
            Keyboards.KWinVirtualKeyboard.forceActivate();
        }
    }
}
