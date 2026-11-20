// SPDX-License-Identifier: GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Shapes
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kcmutils as KCMUtils
import org.kde.config as KConfig
import "../../../../../win7-classic/popup-backend" as PopupBackend

PlasmoidItem {
    id: root
    readonly property alias trayGlyph: glyph
    activationTogglesExpanded: false
    Plasmoid.onActivated: root.togglePopup()
    Plasmoid.icon: root.volumeIcon
    Plasmoid.status: PlasmaCore.Types.ActiveStatus
    toolTipMainText: qsTr("Audio Volume")
    toolTipSubText: audio.available ? qsTr("%1: %2%").arg(audio.device).arg(audio.percent) : qsTr("No audio output")

    readonly property bool canConfigure: KConfig.KAuthorized.authorizeControlModule("kcm_pulseaudio")
    readonly property string volumeIcon: !audio.available || audio.muted || audio.percent === 0 ? "audio-volume-muted-symbolic"
        : audio.percent <= 33 ? "audio-volume-low-symbolic" : audio.percent <= 66 ? "audio-volume-medium-symbolic" : "audio-volume-high-symbolic"

    function togglePopup() {
        if (popup.visible) {
            popup.close();
        } else if (trigger.Window.window) {
            const containment = Plasmoid.containment;
            const work = containment.availableScreenRect;
            const y = trigger.mapToGlobal(0, 0).y;
            // The live cell is inset inside the panel, but the popup must clear the whole panel.
            popupAnchor.y = Plasmoid.location === PlasmaCore.Types.BottomEdge
                ? Math.min(0, containment.screenGeometry.y + work.y + work.height - y) : 0;
            popup.visible = true;
            popup.requestActivate();
            level.forceActiveFocus(Qt.PopupFocusReason);
        }
    }

    function openMixer() {
        popup.close();
        KCMUtils.KCMLauncher.openSystemSettings("kcm_pulseaudio");
    }

    PopupBackend.Audio { id: audio }

    // An applet without a full representation takes its input from the root contents.
    MouseArea {
        id: trigger
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        hoverEnabled: true
        property int wheelDelta: 0
        onClicked: mouse => {
            if (mouse.button === Qt.MiddleButton)
                audio.invokeAudioShortcut("mute");
            else if (mouse.button === Qt.LeftButton)
                root.togglePopup();
        }
        onWheel: wheel => {
            const delta = (wheel.inverted ? -1 : 1) * (wheel.angleDelta.y || -wheel.angleDelta.x);
            if (delta * wheelDelta < 0)
                wheelDelta = 0;
            wheelDelta += delta;
            while (Math.abs(wheelDelta) >= 120) {
                const up = wheelDelta > 0;
                wheelDelta += up ? -120 : 120;
                audio.invokeAudioShortcut((up ? "increase_volume" : "decrease_volume") + ((wheel.modifiers & Qt.ShiftModifier) ? "_small" : ""));
            }
        }
        TapHandler {
            parent: trigger.Window.window ? trigger.Window.window.contentItem : trigger
            enabled: popup.visible
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onTapped: (point, button) => {
                if (button !== Qt.LeftButton || !trigger.contains(trigger.mapFromItem(null, point.scenePosition)))
                    popup.close();
            }
        }
        Item { id: popupAnchor; width: parent.width; height: parent.height }
        Kirigami.Icon { id: glyph; anchors.fill: parent; source: root.volumeIcon }
    }

    PlasmaCore.Dialog {
        id: popup
        visualParent: popupAnchor
        location: Plasmoid.location
        type: PlasmaCore.Dialog.AppletPopup
        backgroundHints: PlasmaCore.Dialog.NoBackground
        hideOnWindowDeactivate: true
        visible: false

        mainItem: Rectangle {
            implicitWidth: Math.max(70, mixer.implicitWidth + 10)
            implicitHeight: 291
            color: "white"
            border.color: "black"
            Keys.onEscapePressed: popup.close()

            Kirigami.Icon {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 16
                width: 32; height: 32
                source: "audio-card"
                QQC.ToolTip.visible: outputHover.hovered
                QQC.ToolTip.text: audio.available ? audio.device : qsTr("No audio output")
                HoverHandler { id: outputHover }
            }

            QQC.Slider {
                id: level
                anchors.horizontalCenter: parent.horizontalCenter
                y: 68
                width: 26; height: 117
                padding: 5
                orientation: Qt.Vertical
                from: 0; to: 100; stepSize: 1
                enabled: audio.writable
                value: Math.min(to, audio.percent)
                onMoved: audio.setPercent(Math.round(value))
                Accessible.name: qsTr("Volume")
                Accessible.description: root.toolTipSubText
                QQC.ToolTip.visible: level.hovered || level.pressed
                QQC.ToolTip.text: qsTr("%1%").arg(level.pressed ? Math.round(level.value) : audio.percent)

                background: Item {
                    anchors.fill: parent
                    Rectangle { x: 3; y: 1; width: 1; height: parent.height - 2; color: "#808080" }
                    Rectangle { x: 5; y: 1; width: 1; height: parent.height - 2; color: "#d4d0c8" }
                    Shape {
                        anchors.fill: parent
                        ShapePath {
                            strokeColor: "transparent"; fillColor: "#e4e4e4"
                            startX: 8; startY: 1
                            PathLine { x: 24; y: 1 }
                            PathLine { x: 8; y: level.height - 1 }
                            PathLine { x: 8; y: 1 }
                        }
                    }
                    Repeater {
                        model: 3
                        Rectangle {
                            required property int index
                            x: 8; y: 1 + Math.floor(index * (level.height - 2) / 2)
                            width: 16; height: 1; color: "#ccc"
                        }
                    }
                }
                handle: Shape {
                    x: 0
                    y: Math.round((1 - level.position) * (level.height - height))
                    width: 21; height: 11
                    ShapePath {
                        strokeColor: "#404040"; strokeWidth: 1; fillColor: "#d4d0c8"
                        startX: 0.5; startY: 0.5
                        PathLine { x: 14.5; y: 0.5 }
                        PathLine { x: 20.5; y: 5.5 }
                        PathLine { x: 14.5; y: 10.5 }
                        PathLine { x: 0.5; y: 10.5 }
                        PathLine { x: 0.5; y: 0.5 }
                    }
                }
            }

            QQC.Button {
                id: mute
                anchors.horizontalCenter: parent.horizontalCenter
                y: 201
                width: 26; height: 25
                background: Rectangle {
                    color: mute.pressed ? "#d4d0c8" : "white"
                    border.color: mute.hovered || mute.activeFocus ? "#808080" : "white"
                }
                contentItem: Kirigami.Icon { source: root.volumeIcon }
                enabled: audio.available
                onClicked: audio.toggleMute()
                Accessible.name: audio.muted ? qsTr("Unmute") : qsTr("Mute")
            }

            QQC.Button {
                id: mixer
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 1 }
                height: 42
                text: qsTr("Mixer")
                enabled: root.canConfigure
                onClicked: root.openMixer()
                contentItem: Text {
                    text: mixer.text
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: mixer.enabled ? "black" : "#808080"
                    renderType: Text.NativeRendering
                }
                background: Rectangle {
                    color: mixer.pressed ? "#aca899" : "#d4d0c8"
                    Rectangle { width: parent.width; height: 1; color: "#808080" }
                    Rectangle { y: 1; width: parent.width; height: 1; color: "white" }
                }
            }
        }
    }

    Plasmoid.contextualActions: PlasmaCore.Action {
        text: qsTr("Configure Audio Devices…")
        icon.name: "configure"
        visible: root.canConfigure
        onTriggered: root.openMixer()
    }
}
