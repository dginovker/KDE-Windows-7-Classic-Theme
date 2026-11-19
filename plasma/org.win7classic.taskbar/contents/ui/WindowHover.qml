pragma ComponentBehavior: Bound

import QtQuick
import "../../../../../win7-classic/primitives2" as Classic
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

PlasmaCore.Dialog {
    id: popup
    required property Item anchor
    required property bool ownerHovered
    required property string titleText
    required property var windowIcon
    required property bool canClose
    signal activateWindow
    signal closeWindow

    visualParent: anchor
    type: PlasmaCore.Dialog.Dock
    readonly property bool pressed: activateMouse.pressed || closeMouse.pressed
    flags: Qt.WindowStaysOnTopHint | (pressed ? 0 : Qt.WindowDoesNotAcceptFocus)
    backgroundHints: PlasmaCore.Dialog.NoBackground
    location: PlasmaCore.Types.Floating

    function closeTarget(): void {
        visible = false
        closeWindow()
    }

    // Passive hover does not request activation. Native Escape is a shell-wide key;
    // do not intercept the focused client’s input on Wayland.
    function open(): void { visible = true }
    function enteredButton(): void { leave.stop() }
    function leftButton(): void {
        if (visible && !hover.hovered)
            leave.restart()
    }
    onVisibleChanged: if (!visible) leave.stop()

    property Timer leaveTimer: Timer {
        id: leave
        interval: 420
        onTriggered: popup.visible = false
    }

    mainItem: Classic.Raster {
        id: body
        width: 154; height: 47
        edge: Classic.Raster.Raised
        fill: Classic.Palette.face
        HoverHandler {
            id: hover
            onHoveredChanged: {
                if (!popup.visible)
                    return
                if (hovered || popup.ownerHovered)
                    leave.stop()
                else
                    leave.restart()
            }
        }
        Rectangle {
            x: 5; y: 13; width: 145; height: 28
            color: Classic.Palette.face
            readonly property bool hot: popup.ownerHovered || hover.hovered || popup.pressed
            border.color: !hot ? color : popup.pressed ? "white" : "#808080"
            Rectangle {
                visible: parent.hot
                width: parent.width - 1; height: 1
                color: popup.pressed ? "#808080" : "white"
            }
            Rectangle {
                visible: parent.hot
                width: 1; height: parent.height - 1
                color: popup.pressed ? "#808080" : "white"
            }
            Kirigami.Icon {
                x: 15; y: 6; width: 16; height: 16
                source: popup.windowIcon
            }
            Text {
                x: 36; width: 72; height: parent.height
                text: popup.titleText
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                font.family: "Tahoma"; font.pixelSize: 11
                color: "black"
                renderType: Text.NativeRendering
            }
            MouseArea {
                id: activateMouse
                anchors.fill: parent
                onPressed: popup.requestActivate()
                onClicked: {
                    popup.visible = false
                    popup.activateWindow()
                }
            }
            Image {
                x: 114; y: 7; width: 14; height: 14
                source: "window-hover-close.png"
                visible: parent.hot && popup.canClose
                Accessible.role: Accessible.Button
                Accessible.name: qsTr("Close window")
                Accessible.onPressAction: popup.closeTarget()
                MouseArea {
                    id: closeMouse
                    anchors.fill: parent
                    onPressed: popup.requestActivate()
                    onClicked: popup.closeTarget()
                }
            }
        }
    }
}
