pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore

ContainmentItem {
    id: tray

    readonly property int pitch: 24
    property int cellRevision: 0
    property int expandedChildren: 0
    readonly property var ownedBackend: Plasmoid
    readonly property var notifiers: ownedBackend.statusNotifiers
    readonly property var visibleSnis: notifiers?.items.filter(n => notifierPlacement(n) === 2) ?? []
    readonly property var hiddenSnis: notifiers?.items.filter(n => notifierPlacement(n) === 1) ?? []
    readonly property var configured: Plasmoid.configuration
    readonly property var hidden: Containment.applets.filter(a => placement(a) === 1)
    readonly property var shown: Containment.applets.filter(a => placement(a) === 2)

    Layout.minimumWidth: rail.implicitWidth
    Layout.maximumWidth: rail.implicitWidth
    Layout.minimumHeight: 24

    function placement(applet) {
        const id = applet.pluginName;
        if (configured.showAllItems || configured.shownItems.includes(id)) {
            return 2;
        }
        if (applet.status === PlasmaCore.Types.HiddenStatus) {
            return 0;
        }
        return configured.hiddenItems.includes(id) || applet.status === PlasmaCore.Types.PassiveStatus ? 1 : 2;
    }

    function notifierPlacement(item) {
        const id = item.persistentId;
        if (configured.showAllItems || configured.shownItems.includes(id)) {
            return 2;
        }
        if (configured.disabledStatusNotifiers.includes(id)) {
            return 0;
        }
        return configured.hiddenItems.includes(id) || item.Status === "Passive" ? 1 : 2;
    }

    Component {
        id: sniComponent
        Controls.AbstractButton {
            id: notifier
            required property var modelData
            width: tray.pitch
            height: tray.pitch
            focusPolicy: Qt.StrongFocus
            Accessible.name: modelData.Title || modelData.Id
            Controls.ToolTip.visible: hovered
            Controls.ToolTip.text: Accessible.name
            function send(method) {
                tray.notifiers.trigger(modelData.address, method, notifier);
            }
            onClicked: send("Activate")
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Menu) {
                    send("ContextMenu");
                    event.accepted = true;
                }
            }
            contentItem: Item {
                Kirigami.Icon {
                    anchors.centerIn: parent
                    width: 22
                    height: 22
                    source: notifier.modelData.icon
                }
                Kirigami.Icon {
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    width: 11
                    height: 11
                    source: notifier.modelData.overlay
                }
            }
            TapHandler {
                acceptedButtons: Qt.RightButton | Qt.MiddleButton
                onTapped: (point, button) => notifier.send(button === Qt.RightButton ? "ContextMenu" : "SecondaryActivate")
            }
            WheelHandler {
                onWheel: event => {
                    if (event.angleDelta.y !== 0) {
                        tray.notifiers.scroll(notifier.modelData.address, event.angleDelta.y, "vertical");
                    }
                }
            }
            WheelHandler {
                orientation: Qt.Horizontal
                onWheel: event => {
                    if (event.angleDelta.x !== 0) {
                        tray.notifiers.scroll(notifier.modelData.address, event.angleDelta.x, "horizontal");
                    }
                }
            }
        }
    }

    function hostedCell(deck, applet, revision) {
        for (let i = 0; i < deck.count; ++i) {
            const cell = deck.itemAt(i);
            if (cell?.modelData === applet) {
                return cell;
            }
        }
        return null;
    }

    Component {
        id: cellComponent
        Item {
            required property var modelData
            width: tray.pitch
            height: tray.pitch
            TapHandler {
                acceptedButtons: Qt.RightButton
                onTapped: tray.ownedBackend.showAppletMenu(parent.modelData, parent)
            }
        }
    }

    Connections {
        target: tray.ownedBackend
        function onActivated() {
            if (tray.hidden.length || tray.hiddenSnis.length) {
                overflow.visible = !overflow.visible;
            }
        }
    }

    Row {
        id: rail
        anchors.verticalCenter: parent.verticalCenter
        layoutDirection: Qt.LeftToRight
        Controls.AbstractButton {
            width: 18
            height: tray.pitch
            visible: tray.hidden.length > 0 || tray.hiddenSnis.length > 0
            focusPolicy: Qt.StrongFocus
            Accessible.name: overflow.visible ? qsTr("Close hidden icons") : qsTr("Show hidden icons")
            onClicked: overflow.visible = !overflow.visible
            contentItem: Item {
                Image {
                    anchors.centerIn: parent
                    source: Qt.resolvedUrl("show-hidden.png")
                    width: 5
                    height: 8
                    smooth: false
                }
            }
        }
        Repeater { model: tray.visibleSnis; delegate: sniComponent }
        Repeater {
            id: visibleCells
            model: tray.shown
            delegate: cellComponent
            onItemAdded: tray.cellRevision++
            onItemRemoved: tray.cellRevision++
        }
    }

    PlasmaCore.AppletPopup {
        id: overflow
        appletInterface: tray
        visualParent: rail
        popupDirection: Qt.TopEdge
        hideOnWindowDeactivate: !tray.configured.pin && tray.expandedChildren === 0
        mainItem: Row {
            Repeater { model: tray.hiddenSnis; delegate: sniComponent }
            Repeater {
                id: hiddenCells
                model: tray.hidden
                delegate: cellComponent
                onItemAdded: tray.cellRevision++
                onItemRemoved: tray.cellRevision++
            }
        }
    }

    Repeater {
        model: Containment.applets
        delegate: Item {
            id: hosted
            required property var modelData
            readonly property var nativeItem: tray.itemFor(modelData)
            readonly property var slot: tray.hostedCell(visibleCells, modelData, tray.cellRevision)
                                        || (overflow.visible ? tray.hostedCell(hiddenCells, modelData, tray.cellRevision) : null)
            // Leave hidden applets in the panel until the overflow is opened, so their shortcuts are alive.
            readonly property Item holder: slot || hosted
            readonly property bool overflowChildExpanded: !!(nativeItem?.expanded && tray.hidden.includes(modelData))
            onOverflowChildExpandedChanged: tray.expandedChildren += overflowChildExpanded ? 1 : -1
            Component.onDestruction: {
                if (overflowChildExpanded) {
                    tray.expandedChildren--;
                }
            }
            readonly property var compact: nativeItem?.compactRepresentationItem
            readonly property string art: {
                if (!compact || !slot || slot.parent !== rail) {
                    return "";
                }
                switch (modelData.pluginName) {
                case "org.kde.plasma.volume":
                    return tray.ownedBackend.speakerArt;
                case "org.kde.plasma.networkmanagement":
                    return modelData.icon === "network-wired-disconnected-symbolic" ? "ethernet-disconnected.png" : "";
                default:
                    return "";
                }
            }
            Binding {
                target: hosted.compact
                property: "opacity"
                value: 0
                when: !!hosted.compact && !!hosted.art
            }
            Image {
                parent: hosted.holder
                x: 4
                y: 4
                z: 1
                width: 16
                height: 16
                smooth: false
                visible: hosted.art.length > 0
                source: hosted.art ? Qt.resolvedUrl(hosted.art) : ""
            }
            Binding { target: hosted.nativeItem; property: "parent"; value: hosted.holder; when: !!hosted.nativeItem }
            Binding { target: hosted.nativeItem; property: "x"; value: 1; when: !!hosted.nativeItem }
            Binding { target: hosted.nativeItem; property: "y"; value: 1; when: !!hosted.nativeItem }
            Binding { target: hosted.nativeItem; property: "width"; value: 22; when: !!hosted.nativeItem }
            Binding { target: hosted.nativeItem; property: "height"; value: 22; when: !!hosted.nativeItem }
            Binding { target: hosted.nativeItem; property: "visible"; value: !!hosted.slot; when: !!hosted.nativeItem }
        }
    }
}
