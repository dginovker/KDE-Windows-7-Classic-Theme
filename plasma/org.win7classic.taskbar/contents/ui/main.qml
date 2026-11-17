import QtQuick
import "../../../../../win7-classic/primitives2" as Classic
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import org.kde.taskmanager as TaskManager

// Geometry is in panel-window pixels measured from reference/screenshots/w7-taskbar.png (panel top = screen y 756).
// Plasma's panel insets applets by at least 4px, so content is placed in window coordinates and may extend past the applet.
PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    Plasmoid.constraintHints: Plasmoid.CanFillArea

    readonly property int buttonY: 4
    readonly property int buttonHeight: 38
    readonly property int tasksX: 63
    readonly property int spacing: 2
    readonly property int launcherWidth: 48
    readonly property int maxWindowWidth: 160
    readonly property int minWindowWidth: 60

    Component.onCompleted: {
        if (Qt.fontFamilies().indexOf("Tahoma") < 0)
            console.error("win7-classic: font family 'Tahoma' is not installed; run install.sh. Text will use a substitute font.");
    }

    property double menuClosedAt: 0
    function toggleMenu() {
        // Clicking Start while the menu is open first deactivates (and hides) the menu; don't reopen it.
        if (startMenu.visible || Date.now() - menuClosedAt < 300)
            startMenu.close();
        else
            startMenu.open();
    }
    Plasmoid.onActivated: toggleMenu()
    StartMenu {
        id: startMenu
        applet: root
        onVisibleChanged: if (!visible) root.menuClosedAt = Date.now()
    }

    TaskManager.VirtualDesktopInfo { id: virtualDesktopInfo }
    TaskManager.ActivityInfo { id: activityInfo }
    TaskManager.TasksModel {
        id: tasksModel
        groupMode: TaskManager.TasksModel.GroupDisabled
        sortMode: TaskManager.TasksModel.SortManual
        // Windows 7 puts a running app's window button where its pinned launcher was.
        separateLaunchers: false
        launchInPlace: true
        hideActivatedLaunchers: true
        launcherList: Plasmoid.configuration.launchers
        virtualDesktop: virtualDesktopInfo.currentDesktop
        activity: activityInfo.currentActivity
        screenGeometry: Plasmoid.containment.screenGeometry
        filterByVirtualDesktop: true
        filterByActivity: true
        filterByScreen: true
    }

    TaskMenu {
        id: taskMenu
        tasks: tasksModel
    }

    fullRepresentation: Item {
        id: area
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumWidth: root.tasksX + root.launcherWidth
        property point origin: Qt.point(0, 0)
        function syncOrigin() { origin = mapToItem(null, 0, 0) }
        Component.onCompleted: Qt.callLater(syncOrigin)
        onWidthChanged: Qt.callLater(syncOrigin)
        onHeightChanged: Qt.callLater(syncOrigin)
        Connections { target: area.Window.window; function onWidthChanged() { Qt.callLater(area.syncOrigin) } }

        readonly property int launchers: tasksModel.launcherCount
        readonly property int windows: tasksModel.count - launchers
        readonly property int windowWidth: windows === 0 ? root.maxWindowWidth : Math.max(root.minWindowWidth, Math.min(root.maxWindowWidth,
            Math.floor((width + origin.x - root.tasksX - launchers * root.launcherWidth - (tasksModel.count - 1) * root.spacing) / windows)))

        Bevel {
            id: start
            x: 2 - area.origin.x; y: root.buttonY - area.origin.y; width: 52; height: root.buttonHeight
            sunken: startMouse.pressed || startMenu.visible
            Image {
                x: 2 + (start.sunken ? 1 : 0); y: 11 + (start.sunken ? 1 : 0)
                width: 18; height: 14
                source: "flag.svg"
                sourceSize: Qt.size(18, 14)
            }
            Text {
                x: 20 + (start.sunken ? 1 : 0); y: (start.sunken ? 1 : 0)
                height: parent.height
                verticalAlignment: Text.AlignVCenter
                text: "Start"
                font.family: "Tahoma"; font.pixelSize: 11; font.bold: true
                color: "black"
                renderType: Text.NativeRendering
            }
            Classic.Raster {
                x: 19; y: 3; width: 30; height: 32
                focused: startMenu.visible && !startMenu.hotTracking
                patternOrigin: Qt.point(21, 763)
            }
            MouseArea {
                id: startMouse
                anchors.fill: parent
                onClicked: root.toggleMenu()
            }
        }

        Row {
            id: taskRow
            x: root.tasksX - area.origin.x; y: root.buttonY - area.origin.y
            spacing: root.spacing
            property int dragIndex: -1
            property int dropIndex: -1
            property real dragOffset: 0
            property real dragWidth: 0
            Repeater {
                id: taskRepeater
                model: tasksModel
                delegate: Item {
                    id: task
                    required property var model
                    required property int index
                    readonly property bool launcher: model.IsLauncher === true
                    readonly property bool active: model.IsActive === true && model.IsMinimized !== true
                    readonly property bool sunken: (active && !launcher) || mouse.pressed || (taskMenu.visible && taskMenu.taskButton === task)
                    readonly property int shift: sunken ? 1 : 0
                    width: launcher ? root.launcherWidth : area.windowWidth
                    height: root.buttonHeight

                    Item {
                        width: task.width; height: task.height
                        x: taskRow.dragIndex === task.index ? taskRow.dragOffset
                           : taskRow.dragIndex < 0 ? 0
                           : task.index > taskRow.dragIndex && task.index <= taskRow.dropIndex ? -taskRow.dragWidth - root.spacing
                           : task.index < taskRow.dragIndex && task.index >= taskRow.dropIndex ? taskRow.dragWidth + root.spacing : 0
                        Behavior on x { enabled: taskRow.dragIndex !== task.index; NumberAnimation { duration: 140 } }
                        z: taskRow.dragIndex === task.index ? 1 : 0
                        Bevel {
                            anchors.fill: parent
                            visible: !task.launcher || mouse.containsMouse || mouse.pressed
                            sunken: task.sunken
                            fill: task.active && !task.launcher ? Classic.Palette.highlight3D : Classic.Palette.face
                        }
                        Kirigami.Icon {
                            x: (task.launcher ? (task.width - 32) / 2 : 3) + task.shift
                            y: 3 + task.shift
                            width: 32; height: 32
                            source: task.model.decoration
                        }
                        Text {
                            visible: !task.launcher
                            x: 39 + task.shift; y: task.shift
                            width: task.width - x - 4; height: task.height
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            text: task.model.display
                            font.family: "Tahoma"; font.pixelSize: 11; font.bold: task.active
                            color: "black"
                            renderType: Text.NativeRendering
                        }
                    }
                    z: taskRow.dragIndex === task.index ? 1 : 0
                    TaskTooltip {
                        id: tooltip
                        button: task
                        text: task.model.display
                        pointer: Qt.point(mouse.mouseX, mouse.mouseY)
                    }
                    Timer {
                        id: hoverTimer
                        interval: 700
                        onTriggered: if (mouse.containsMouse && !mouse.pressed && !taskMenu.visible) tooltip.visible = true
                    }
                    MouseArea {
                        id: mouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        onEntered: hoverTimer.restart()
                        onExited: { hoverTimer.stop(); tooltip.visible = false; }
                        property bool dragged: false
                        property real pressX: 0
                        onPressed: (event) => { hoverTimer.stop(); tooltip.visible = false; dragged = false; pressX = event.x; }
                        onPositionChanged: (event) => {
                            if (!(pressedButtons & Qt.LeftButton) || (!dragged && Math.abs(event.x - pressX) < Qt.styleHints.startDragDistance))
                                return;
                            dragged = true;
                            taskRow.dragIndex = task.index;
                            taskRow.dragWidth = task.width;
                            taskRow.dragOffset = event.x - pressX;
                            const center = task.x + task.width / 2 + taskRow.dragOffset;
                            let target = task.index;
                            for (let i = 0; i < taskRepeater.count; ++i) {
                                const other = taskRepeater.itemAt(i);
                                if (i < task.index && center < other.x + other.width / 2)
                                    target = Math.min(target, i);
                                if (i > task.index && center > other.x + other.width / 2)
                                    target = Math.max(target, i);
                            }
                            taskRow.dropIndex = target;
                        }
                        onCanceled: { taskRow.dragIndex = -1; taskRow.dropIndex = -1; }
                        onReleased: {
                            if (!dragged)
                                return;
                            // Keep delegates alive during the grab; moving the model destroys their QML contexts.
                            const from = task.index, to = taskRow.dropIndex;
                            const model = tasksModel, config = Plasmoid.configuration;
                            taskRow.dragIndex = -1;
                            taskRow.dropIndex = -1;
                            if (from !== to) {
                                model.move(from, to);
                                model.syncLaunchers();
                                config.launchers = model.launcherList;
                            }
                        }
                        onClicked: (event) => {
                            if (dragged)
                                return;
                            if (event.button === Qt.RightButton) {
                                taskMenu.open(task);
                                return;
                            }
                            const index = tasksModel.makeModelIndex(task.index);
                            if (task.launcher)
                                tasksModel.requestNewInstance(index);
                            else if (task.active)
                                tasksModel.requestToggleMinimized(index);
                            else
                                tasksModel.requestActivate(index);
                        }
                    }
                }
            }
        }
    }
}
