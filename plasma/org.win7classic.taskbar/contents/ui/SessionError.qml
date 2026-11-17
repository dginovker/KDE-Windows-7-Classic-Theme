import QtQuick
import QtQuick.Window
import org.kde.kirigami as Kirigami
import "../../../../../win7-classic/primitives2" as Classic

Window {
    id: dialog
    property string message: ""
    flags: Qt.Dialog | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint
    // The Start popup has already closed when an asynchronous failure arrives.
    transientParent: null
    modality: Qt.ApplicationModal
    width: 400
    height: Math.max(130, label.implicitHeight + 80)
    color: Classic.Palette.face
    x: Screen.virtualX + (Screen.width - width) / 2
    y: Screen.virtualY + (Screen.height - height) / 2

    function show(action, error, member) {
        title = action;
        message = action + " failed.\n\n" + error.name + "\n" + error.message;
        console.error("win7-classic: logind." + member + ": " + message);
        visible = true;
        requestActivate();
        body.forceActiveFocus();
    }

    Item {
        id: body
        anchors.fill: parent
        focus: true
        Keys.onEscapePressed: dialog.close()
        Keys.onReturnPressed: dialog.close()
        Keys.onEnterPressed: dialog.close()
        Kirigami.Icon { x: 16; y: 16; width: 32; height: 32; source: "dialog-error" }
        Text {
            id: label
            x: 64; y: 16; width: parent.width - 80
            text: dialog.message
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            font.family: "Tahoma"; font.pixelSize: 11
            color: Classic.Palette.text
            renderType: Text.NativeRendering
        }
        Classic.Raster {
            x: (parent.width - width) / 2; y: parent.height - 39
            width: 75; height: 23
            button: true
            pressed: accept.pressed && accept.containsMouse
            Classic.Raster { x: 4; y: 4; width: 67; height: 15; focused: true }
            Text {
                anchors.fill: parent
                text: "OK"
                font.family: "Tahoma"; font.pixelSize: 11
                color: Classic.Palette.text
                renderType: Text.NativeRendering
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            MouseArea { id: accept; anchors.fill: parent; onClicked: dialog.close() }
        }
    }
}
