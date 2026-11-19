import QtQuick
import "../../../../../win7-classic/primitives2" as Classic
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

// Geometry follows the action block in reference/screenshots/w7-explorer-jumplist.png.
PlasmaCore.Dialog {
    id: menu
    required property var tasks
    property Item taskButton: null
    readonly property bool launcher: taskButton !== null && taskButton.launcher
    readonly property bool pinned: taskButton !== null && (launcher || taskButton.model.HasLauncher === true)
    property bool activeOnOpen: false
    property int current: -1
    type: PlasmaCore.Dialog.PopupMenu
    flags: Qt.WindowStaysOnTopHint
    backgroundHints: PlasmaCore.Dialog.NoBackground
    hideOnWindowDeactivate: true
    location: PlasmaCore.Types.Floating
    visualParent: taskButton ? taskButton.popupAnchor : null
    onTaskButtonChanged: if (!taskButton) visible = false

    function open(button) {
        // On Wayland QScreen's available geometry does not exclude Plasma's reserved panels.
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
        current = -1;
        visible = true;
        requestActivate();
        body.forceActiveFocus();
    }
    function trigger(row) {
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
        height: menu.launcher ? 72 : 94
        fill: Classic.Palette.face
        flatBorder: true
        focus: true
        Keys.onEscapePressed: menu.visible = false
        Keys.onDownPressed: menu.current = (menu.current + 1) % rows.count
        Keys.onUpPressed: menu.current = menu.current < 0 ? rows.count - 1 : (menu.current + rows.count - 1) % rows.count
        Keys.onReturnPressed: if (menu.current >= 0) menu.trigger(menu.current)
        Keys.onEnterPressed: if (menu.current >= 0) menu.trigger(menu.current)
        Repeater {
            id: rows
            model: menu.launcher ? 2 : 3
            delegate: Rectangle {
                id: row
                required property int index
                x: 5; y: 15 + index * 22
                width: body.width - 10; height: 22
                color: menu.current === index ? Classic.Palette.selection : "transparent"
                Kirigami.Icon {
                    visible: row.index === 0
                    x: 4; y: 3; width: 16; height: 16
                    source: menu.taskButton ? menu.taskButton.model.decoration : ""
                }
                Image {
                    visible: row.index > 0
                    x: 3; y: 3; width: 16; height: 16
                    source: row.index === 1 ? "jumplist-pin.png" : "jumplist-close.png"
                }
                Text {
                    x: 25; height: parent.height; width: parent.width - x - 2
                    verticalAlignment: Text.AlignVCenter
                    text: row.index === 0 ? (menu.taskButton ? menu.taskButton.model.AppName : "")
                        : row.index === 1 ? (menu.pinned ? "Unpin this program from taskbar" : "Pin this program to taskbar") : "Close window"
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
