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
    property var visibleEntries: []
    property var hiddenEntries: []
    readonly property var notifierItems: notifiers?.items ?? []
    readonly property var stockApplets: Containment.applets
    property var appletHosts: new Map()
    readonly property var configured: Plasmoid.configuration
    readonly property bool hasOverflow: hiddenEntries.length > 0

    function toggleOverflow() {
        if (hasOverflow) {
            overflow.visible = !overflow.visible;
        }
    }
    onHasOverflowChanged: if (!hasOverflow) overflow.visible = false
    onNotifierItemsChanged: queueEntries()
    onStockAppletsChanged: Qt.callLater(updateHosts)
    Component.onCompleted: {
        updateHosts();
        console.info("Classic notification area ready:", Plasmoid.id);
    }

    // Applets can publish a new status as they are reparented into a visible cell.
    function queueEntries() { Qt.callLater(updateEntries); }
    function updateHosts() {
        // Rebuilding existing holders would restore their old geometry bindings over the new ones.
        for (const [applet, host] of appletHosts) {
            if (!stockApplets.includes(applet)) {
                appletHosts.delete(applet);
                host.destroy();
            }
        }
        for (const applet of stockApplets) {
            if (!appletHosts.has(applet)) {
                appletHosts.set(applet, hostComponent.createObject(tray, {modelData: applet}));
            }
        }
        queueEntries();
    }
    function updateEntries() {
        const same = (old, next) => old.length === next.length && next.every((entry, i) =>
            entry.applet === old[i].applet && entry.notifier === old[i].notifier);
        const shown = entriesAt(2);
        const hidden = entriesAt(1);
        if (!same(visibleEntries, shown)) visibleEntries = shown;
        if (!same(hiddenEntries, hidden)) hiddenEntries = hidden;
    }
    Connections {
        target: tray.configured
        function onShowAllItemsChanged() { tray.queueEntries(); }
        function onShownItemsChanged() { tray.queueEntries(); }
        function onHiddenItemsChanged() { tray.queueEntries(); }
        function onDisabledStatusNotifiersChanged() { tray.queueEntries(); }
    }
    readonly property var categoryOrder: ["UnknownCategory", "ApplicationStatus", "Communications", "SystemServices", "Hardware"]

    function entriesAt(position) {
        const rows = stockApplets.filter(a => placement(a) === position).map(a => ({
            applet: a, name: a.title, category: ownedBackend.category(a)
        }));
        for (const n of notifierItems) {
            if (notifierPlacement(n) === position) {
                rows.push({ notifier: n, name: n.Title, category: n.Category });
            }
        }
        rows.sort((a, b) => {
            const last = entry => entry.applet?.pluginName === "org.kde.plasma.notifications" ? 1 : 0;
            const rank = entry => Math.max(0, categoryOrder.indexOf(entry.category));
            return last(a) - last(b) || rank(a) - rank(b) || (a.name || "").localeCompare(b.name || "");
        });
        return rows;
    }

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
            property var modelData
            width: tray.pitch
            height: tray.pitch
            focusPolicy: Qt.StrongFocus
            Accessible.name: modelData?.Title || modelData?.Id || ""
            Controls.ToolTip.visible: hovered
            Controls.ToolTip.text: Accessible.name
            function send(method) {
                tray.notifiers.trigger(modelData.address, method, notifier);
            }
            onClicked: send("Activate")
            Keys.onReturnPressed: send("Activate")
            Keys.onEnterPressed: send("Activate")
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
                    source: notifier.modelData?.icon ?? ""
                }
                Kirigami.Icon {
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    width: 11
                    height: 11
                    source: notifier.modelData?.overlay ?? ""
                }
            }
            TapHandler {
                acceptedButtons: Qt.RightButton | Qt.MiddleButton
                onTapped: (point, button) => notifier.send(button === Qt.RightButton ? "ContextMenu" : "SecondaryActivate")
            }
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.NoButton
                onWheel: event => {
                    if (event.angleDelta.y !== 0) {
                        tray.notifiers.scroll(notifier.modelData.address, event.angleDelta.y, "vertical");
                    }
                    if (event.angleDelta.x !== 0) {
                        tray.notifiers.scroll(notifier.modelData.address, event.angleDelta.x, "horizontal");
                    }
                }
            }
        }
    }

    readonly property Item notificationArea: tray

    // Consumers can anchor to a real mapped cell, never activate the applet through this API.
    function cellForPlugin(pluginId) {
        const applet = Containment.applets.find(item => item.pluginName === pluginId);
        return applet ? (hostedCell(visibleCells, applet, cellRevision)
                         || (overflow.visible ? hostedCell(hiddenCells, applet, cellRevision) : null)) : null;
    }

    function hostedCell(deck, applet, revision) {
        for (let i = 0; i < deck.count; ++i) {
            const cell = deck.itemAt(i);
            if (cell?.modelData.applet === applet) {
                return cell;
            }
        }
        return null;
    }

    Component {
        id: cellComponent
        Item {
            id: cell
            clip: true
            required property var modelData
            width: tray.pitch
            height: tray.pitch
            activeFocusOnTab: !!modelData.applet
            Accessible.role: Accessible.Button
            Accessible.name: modelData.applet?.title ?? ""
            Accessible.onPressAction: modelData.applet?.activated()
            Keys.onSpacePressed: modelData.applet?.activated()
            Keys.onReturnPressed: modelData.applet?.activated()
            Keys.onEnterPressed: modelData.applet?.activated()
            Keys.onMenuPressed: tray.ownedBackend.showAppletMenu(modelData.applet, cell)
            TapHandler {
                enabled: !!cell.modelData.applet
                acceptedButtons: Qt.RightButton
                onTapped: tray.ownedBackend.showAppletMenu(cell.modelData.applet, cell)
            }
            Loader {
                active: !!cell.modelData.notifier
                sourceComponent: sniComponent
                onLoaded: item.modelData = Qt.binding(() => cell.modelData.notifier)
            }
        }
    }

    Connections {
        target: tray.ownedBackend
        function onActivated() { tray.toggleOverflow(); }
    }

    Row {
        id: rail
        anchors.verticalCenter: parent.verticalCenter
        layoutDirection: Qt.LeftToRight
        Controls.AbstractButton {
            id: marker
            width: 18
            height: tray.pitch
            visible: tray.hasOverflow
            focusPolicy: Qt.StrongFocus
            Accessible.name: overflow.visible ? qsTr("Close hidden icons") : qsTr("Show hidden icons")
            onClicked: tray.toggleOverflow()
            Keys.onReturnPressed: tray.toggleOverflow()
            Keys.onEnterPressed: tray.toggleOverflow()
            Keys.onMenuPressed: tray.ownedBackend.configureTray()
            TapHandler {
                acceptedButtons: Qt.RightButton
                onTapped: tray.ownedBackend.configureTray()
            }
            background: Rectangle {
                visible: marker.hovered || marker.visualFocus || marker.down || overflow.visible
                anchors.fill: parent
                anchors.margins: 1
                color: "transparent"
                border.color: marker.down || overflow.visible ? "#808080" : "#ffffff"
            }
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
        Repeater {
            id: visibleCells
            model: tray.visibleEntries
            delegate: cellComponent
            onItemAdded: tray.cellRevision++
            onItemRemoved: tray.cellRevision++
        }
    }

    PlasmaCore.AppletPopup {
        id: overflow
        appletInterface: tray
        visualParent: marker
        popupDirection: Qt.TopEdge
        hideOnWindowDeactivate: !tray.configured.pin && tray.expandedChildren === 0
        onVisibleChanged: if (visible) {
            requestActivate();
            overflowGrid.forceActiveFocus();
        }
        mainItem: Grid {
            id: overflowGrid
            columns: Math.min(8, Math.max(1, tray.hiddenEntries.length))
            Layout.minimumWidth: implicitWidth
            Layout.preferredWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.minimumHeight: implicitHeight
            Layout.preferredHeight: implicitHeight
            Layout.maximumHeight: implicitHeight
            Keys.onEscapePressed: overflow.visible = false
            Repeater {
                id: hiddenCells
                model: tray.hiddenEntries
                delegate: cellComponent
                onItemAdded: tray.cellRevision++
                onItemRemoved: tray.cellRevision++
            }
        }
    }

    Component {
        id: hostComponent
        Item {
            id: hosted
            required property var modelData
            Connections {
                target: hosted.modelData
                function onStatusChanged() { tray.queueEntries(); }
            }
            readonly property var nativeItem: tray.itemFor(modelData)
            readonly property var slot: tray.hostedCell(visibleCells, modelData, tray.cellRevision)
                                        || (overflow.visible ? tray.hostedCell(hiddenCells, modelData, tray.cellRevision) : null)
            // Leave hidden applets in the panel until the overflow is opened, so their shortcuts are alive.
            readonly property Item holder: slot || hosted
            readonly property bool overflowChildExpanded: !!(nativeItem?.expanded && tray.placement(modelData) === 1)
            onOverflowChildExpandedChanged: tray.expandedChildren += overflowChildExpanded ? 1 : -1
            Component.onDestruction: {
                if (overflowChildExpanded) {
                    tray.expandedChildren--;
                }
            }
            readonly property var compact: nativeItem?.compactRepresentationItem
            readonly property string art: {
                if (!compact || !slot) {
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
