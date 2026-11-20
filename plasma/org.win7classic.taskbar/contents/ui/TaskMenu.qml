import QtQuick
import "../../../../../win7-classic/primitives2" as Classic
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

// Geometry follows reference/screenshots/w7-explorer-jumplist.png.
PlasmaCore.Dialog {
    id: menu
    required property var tasks
    property Item taskButton: null
    readonly property bool launcher: taskButton !== null && taskButton.launcher
    readonly property bool pinned: taskButton !== null && (launcher || taskButton.model.HasLauncher === true)
    property bool activeOnOpen: false
    property int current: -1
    property var frequent: []
    property int checkTicket: 0
    property string frequentStatus: ""
    readonly property int sectionHeight: frequent.length > 0 ? 56 + frequent.length * 22 : frequentStatus ? 43 : 0
    // Native Explorer omits the lead-in and trailing space when it has only actions.
    readonly property bool compact: explorer && !frequent.length
    readonly property bool explorer: taskButton !== null && (taskButton.explorerWindow || (launcher &&
        String(taskButton.model.LauncherUrlWithoutIcon) === "applications:org.win7classic.explorer.desktop"))
    readonly property int fullActionHeight: launcher ? 72 : 94
    readonly property int actionHeight: fullActionHeight - (compact ? 22 : 0)
    readonly property Classic.ExplorerLocations history: Classic.ExplorerLocations {
        id: locations
        onChecked: (ticket, valid, unavailable, rows) => {
            if (ticket !== menu.checkTicket)
                return;
            if (initial.running) {
                initial.stop();
                menu.frequent = rows;
                if (unavailable)
                    menu.showUnavailable("could not check privacy or read history");
                else
                    menu.showMenu();
            } else if (menu.visible && menu.frequentStatus) {
                // Never resize a mapped popup: dismiss if the section must disappear.
                if (valid)
                    menu.frequentStatus = "Reopen to view Frequent";
                else if (!unavailable)
                    menu.visible = false;
            } else if (menu.visible && deadline.running) {
                deadline.stop();
                if (!valid)
                    menu.visible = false;
            }
        }
        onOpened: error => { if (error) failure.showFailure("Windows Explorer", error); }
    }
    type: PlasmaCore.Dialog.PopupMenu
    flags: Qt.WindowStaysOnTopHint
    backgroundHints: PlasmaCore.Dialog.NoBackground
    hideOnWindowDeactivate: true
    location: PlasmaCore.Types.Floating
    visualParent: taskButton ? taskButton.popupAnchor : null
    onTaskButtonChanged: if (!taskButton) {
        cancelPending();
        visible = false;
    }
    onVisibleChanged: if (!visible) {
        deadline.stop();
        frequent = [];
    }

    function cancelPending() {
        // An unmapped dialog cannot get a Wayland deactivation event.
        initial.stop();
    }

    function check(limit, paths) {
        // A refused query does not supersede the response already in flight.
        if (locations.query(checkTicket + 1, limit, paths)) {
            ++checkTicket;
            deadline.restart();
        }
        else if (paths.length)
            visible = false;
    }

    function showUnavailable(reason) {
        console.warn("win7-classic: Frequent unavailable: " + reason);
        frequentStatus = "Frequent unavailable";
        showMenu();
    }

    function showMenu() {
        visible = true;
        requestActivate();
        body.forceActiveFocus();
    }

    function open(button) {
        cancelPending();
        visible = false;
        // QScreen geometry includes Plasma’s reserved panels on Wayland.
        const containment = Plasmoid.containment;
        const work = containment.availableScreenRect;
        const left = containment.screenGeometry.x + work.x;
        const halfWidth = body.width / 2;
        const origin = button.mapToGlobal(0, 0).x;
        const center = Math.round(origin + button.width / 2);
        const clampedCenter = Math.max(left + halfWidth, Math.min(center, left + work.width - halfWidth));
        button.popupAnchor.x = clampedCenter - origin - button.popupAnchor.width / 2;
        taskButton = button;
        activeOnOpen = button.active;
        const room = button.mapToGlobal(0, 0).y - button.Screen.virtualY - 4 - fullActionHeight;
        const limit = Math.min(10, Math.floor((room - 56) / 22));
        current = -1;
        frequent = [];
        frequentStatus = "";
        // Wayland fixes the popup anchor when mapped. Never move the actions under the pointer.
        if (!explorer || limit <= 0)
            showMenu();
        else if (locations.query(checkTicket + 1, limit, [])) {
            ++checkTicket;
            initial.restart();
        } else
            showUnavailable("worker is busy");
    }
    function trigger(row) {
        if (row < frequent.length) {
            const path = frequent[row].path;
            visible = false;
            locations.open(path);
            return;
        }
        row -= frequent.length;
        const index = tasks.makeModelIndex(taskButton.index);
        const url = taskButton.model.LauncherUrlWithoutIcon;
        const wasPinned = pinned;
        visible = false;
        if (row === 0) {
            tasks.requestNewInstance(index);
        } else if (row === 1) {
            const ok = wasPinned ? tasks.requestRemoveLauncher(url) : tasks.requestAddLauncher(url);
            if (!ok)
                throw new Error("win7-classic: could not " + (wasPinned ? "unpin " : "pin ") + url);
            tasks.syncLaunchers();
            Plasmoid.configuration.launchers = tasks.launcherList;
        } else {
            tasks.requestClose(index);
        }
    }

    mainItem: Classic.Raster {
        id: body
        width: 230
        height: menu.actionHeight + menu.sectionHeight
        fill: Classic.Palette.face
        flatBorder: true
        focus: true
        Keys.onEscapePressed: menu.visible = false
        Keys.onDownPressed: menu.current = (menu.current + 1) % rows.count
        Keys.onUpPressed: menu.current = menu.current < 0 ? rows.count - 1 : (menu.current + rows.count - 1) % rows.count
        Keys.onReturnPressed: if (menu.current >= 0) menu.trigger(menu.current)
        Keys.onEnterPressed: if (menu.current >= 0) menu.trigger(menu.current)
        SessionError { id: failure }
        Timer {
            id: initial
            interval: 180
            onTriggered: menu.showUnavailable("initial check timed out")
        }
        Timer {
            id: deadline
            interval: 900
            onTriggered: {
                console.warn("win7-classic: Frequent check timed out");
                if (menu.frequent.length)
                    menu.visible = false;
            }
        }
        Timer {
            interval: 200
            repeat: true
            running: menu.visible && menu.frequent.length > 0
            onTriggered: if (!deadline.running)
                menu.check(0, menu.frequent.map(row => row.path));
        }
        Text {
            visible: menu.sectionHeight > 0
            x: 7; y: 3; height: 18
            verticalAlignment: Text.AlignVCenter
            text: "Frequent"
            font.family: "Tahoma"; font.pixelSize: 11; font.bold: true
            color: "black"
            renderType: Text.NativeRendering
        }
        Text {
            visible: menu.frequentStatus !== ""
            x: 7; y: 23; height: 18
            verticalAlignment: Text.AlignVCenter
            text: menu.frequentStatus
            font.family: "Tahoma"; font.pixelSize: 11
            color: "black"
            renderType: Text.NativeRendering
        }
        Rectangle {
            visible: menu.sectionHeight > 0
            x: 7; y: menu.sectionHeight - 2; width: body.width - 12; height: 1
            color: Classic.Palette.shadow3D
            Rectangle {
                x: 1; y: 1; width: parent.width - 1; height: 1
                color: Classic.Palette.highlight3D
            }
            Rectangle {
                y: 1; width: 1; height: 1
                color: parent.color
            }
        }
        Repeater {
            id: rows
            model: menu.frequent.length + (menu.launcher ? 2 : 3)
            delegate: Rectangle {
                id: row
                required property int index
                readonly property int action: index - menu.frequent.length
                readonly property var folder: action < 0 ? menu.frequent[index] : null
                x: 5; y: folder ? 32 + index * 22 : menu.sectionHeight + (menu.compact ? 5 : 15) + action * 22
                width: body.width - 10; height: 22
                color: menu.current === index ? Classic.Palette.selection : "transparent"
                Kirigami.Icon {
                    visible: row.folder !== null || row.action === 0
                    x: 4; y: 3; width: 16; height: 16
                    source: row.folder ? row.folder.icon : (menu.taskButton ? menu.taskButton.model.decoration : "")
                }
                Image {
                    visible: row.action > 0
                    x: 3; y: 3; width: 16; height: 16
                    source: row.action === 1 ? "jumplist-pin.png" : "jumplist-close.png"
                }
                Text {
                    x: 25; height: parent.height; width: parent.width - x - 2
                    verticalAlignment: Text.AlignVCenter
                    text: row.folder ? row.folder.name : row.action === 0 ? (menu.taskButton ? menu.taskButton.model.AppName : "")
                        : row.action === 1 ? (menu.pinned ? "Unpin this program from taskbar" : "Pin this program to taskbar") : "Close window"
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    font.family: "Tahoma"; font.pixelSize: 11
                    color: menu.current === row.index ? "white" : "black"
                    renderType: Text.NativeRendering
                }
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: menu.current = row.index
                    onExited: menu.current = -1
                    onClicked: menu.trigger(row.index)
                }
            }
        }
    }
}
