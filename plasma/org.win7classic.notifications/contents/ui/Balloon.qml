// SPDX-License-Identifier: GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import org.kde.plasma.core as PlasmaCore
import org.kde.notificationmanager as NM
import org.kde.taskmanager as TaskManager

PlasmaCore.Dialog {
    id: popup
    required property var entry
    required property int row
    required property string notificationId
    required property NM.Notifications source
    required property NM.Settings settings
    required property TaskManager.TasksModel tasks
    required property var focusControl
    required property bool critical
    property bool tailAtBottom: true
    property int tailOffset: 235
    property int availableHeight: 400
    property bool tail: true

    readonly property int tailHeight: tail ? 10 : 0
    readonly property int timeout: !entry ? 0 : entry.timeout === -1 ? settings.popupTimeout + (entry.urls.length > 0 ? 5000 : 0)
        : (entry.type === NM.Notifications.JobType && !settings.permanentJobPopups ? settings.popupTimeout : entry.timeout)
    readonly property double updatedAt: Number(new Date(entry?.updated))

    type: critical ? PlasmaCore.Dialog.CriticalNotification : PlasmaCore.Dialog.Notification
    backgroundHints: PlasmaCore.Dialog.NoBackground
    flags: Qt.FramelessWindowHint | (contents.replying ? 0 : Qt.WindowDoesNotAcceptFocus)
    onVisibleChanged: if (visible) focusControl.setPopupFocus(this, contents.replying)
    visible: false

    function expire() {
        if (entry.type === NM.Notifications.JobType && !settings.permanentJobPopups)
            entry.dismissed = true;
        else if (entry.resident || (contents.hasActions && !entry.transient))
            entry.expired = true;
        else
            source.expire(source.index(row, 0));
    }

    onUpdatedAtChanged: if (expiry.running) expiry.restart()

    mainItem: Item {
        id: surface
        implicitWidth: 272
        implicitHeight: bodyHeight + popup.tailHeight
        readonly property int bodyHeight: Math.min(popup.availableHeight - popup.tailHeight, Math.max(44, contents.implicitHeight + 10))

        Shape {
            width: surface.width
            height: surface.height
            transform: Scale { origin.y: surface.height / 2; yScale: popup.tailAtBottom ? 1 : -1 }
            ShapePath {
                strokeColor: "black"
                strokeWidth: 1
                fillColor: "#ffffe1"
                startX: 4.5; startY: 0.5
                PathLine { x: surface.width - 4.5; y: 0.5 }
                PathQuad { x: surface.width - 0.5; y: 4.5; controlX: surface.width - 0.5; controlY: 0.5 }
                PathLine { x: surface.width - 0.5; y: surface.bodyHeight - 4.5 }
                PathQuad { x: surface.width - 4.5; y: surface.bodyHeight - 0.5; controlX: surface.width - 0.5; controlY: surface.bodyHeight - 0.5 }
                PathLine { x: popup.tailOffset + 9; y: surface.bodyHeight - 0.5 }
                PathLine { x: popup.tailOffset; y: surface.height - 0.5 }
                PathLine { x: popup.tailOffset - 9; y: surface.bodyHeight - 0.5 }
                PathLine { x: 4.5; y: surface.bodyHeight - 0.5 }
                PathQuad { x: 0.5; y: surface.bodyHeight - 4.5; controlX: 0.5; controlY: surface.bodyHeight - 0.5 }
                PathLine { x: 0.5; y: 4.5 }
                PathQuad { x: 4.5; y: 0.5; controlX: 0.5; controlY: 0.5 }
            }
        }

        Flickable {
            x: 6
            y: (popup.tailAtBottom ? 0 : popup.tailHeight) + 5
            width: surface.width - 12
            height: surface.bodyHeight - 10
            contentWidth: width
            contentHeight: contents.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            clip: true

            NotificationContents {
                id: contents
                width: parent.width
                entry: popup.entry
                row: popup.row
                source: popup.source
                tasks: popup.tasks
                onReplyingChanged: popup.focusControl.setPopupFocus(popup, replying)
            }
        }

        HoverHandler {
            id: hover
            onHoveredChanged: if (hovered && popup.entry) popup.entry.read = true
        }
        TapHandler {
            acceptedButtons: Qt.MiddleButton
            enabled: !!popup.entry?.closable
            onTapped: popup.source.close(popup.source.index(popup.row, 0))
        }
    }

    property Timer expiryTimer: Timer {
        id: expiry
        interval: Math.max(1, popup.timeout)
        running: popup.visible && popup.timeout > 0 && !hover.hovered && !(contents.replying && (contents.editing || contents.pendingReply))
        onTriggered: popup.expire()
    }
}
