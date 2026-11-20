// SPDX-License-Identifier: GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQml.Models
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kcmutils as KCMUtils
import org.kde.config as KConfig
import org.kde.notificationmanager as NM
import org.kde.taskmanager as TaskManager
import "../../../../../win7-classic/popup-backend" as PopupBackend

PlasmoidItem {
    id: root
    activationTogglesExpanded: false
    Plasmoid.onActivated: root.toggleHistory()
    Plasmoid.icon: !NM.Server.valid || inhibited ? "notifications-disabled-symbolic"
        : history.unreadNotificationsCount > 0 ? "notification-active-symbolic" : "notification-inactive-symbolic"
    Plasmoid.status: PlasmaCore.Types.ActiveStatus
    toolTipMainText: qsTr("Notifications")
    toolTipSubText: !NM.Server.valid ? qsTr("Plasma notification service unavailable")
        : inhibited ? qsTr("Do not disturb") : qsTr("%n unread notification(s)", "", history.unreadNotificationsCount)

    readonly property Item anchorItem: trigger
    property Item trayHost
    readonly property Item balloonAnchor: trayHost?.cellForPlugin(Plasmoid.pluginName) ?? trayHost?.hiddenIconsAnchor ?? null
    readonly property bool frontendReady: NM.Server.valid && !!trayHost && stock.status === Loader.Ready
    onFrontendReadyChanged: if (frontendReady) console.info("Classic notification frontend ready")
    onBalloonAnchorChanged: Qt.callLater(positionPopups)
    readonly property bool anchored: policy.popupPosition === NM.Settings.CloseToWidget
    readonly property rect workArea: Plasmoid.containment ? Qt.rect(
        Plasmoid.containment.screenGeometry.x + Plasmoid.containment.availableScreenRect.x,
        Plasmoid.containment.screenGeometry.y + Plasmoid.containment.availableScreenRect.y,
        Plasmoid.containment.availableScreenRect.width,
        Plasmoid.containment.availableScreenRect.height) : Qt.rect(0, 0, 0, 0)
    readonly property bool inhibited: stock.item?.inhibited ?? false

    function toggleHistory() {
        if (historyPopup.visible) {
            historyPopup.close();
        } else if (anchorItem?.Window.window && stock.item) {
            stock.item.hideInhibitionSummary();
            historyPopup.visible = true;
        }
    }

    function closePlasmoid() { historyPopup.close(); }
    function clearNotificationHistoryAndShowOsd() {
        if (history.expiredNotificationsCount > 0 || history.activeNotificationsCount > 0) {
            history.clear(NM.Notifications.ClearExpired);
            stock.item.showHistoryCleaned();
        }
    }

    onWorkAreaChanged: Qt.callLater(positionPopups)
    onAnchorItemChanged: Qt.callLater(positionPopups)

    NM.Settings { id: policy; onSettingsChanged: Qt.callLater(root.positionPopups) }
    PopupBackend.BalloonFocus { id: balloonFocus }
    PopupBackend.StockNotificationView { id: stockModule }
    TaskManager.TasksModel { id: taskModel; groupMode: TaskManager.TasksModel.GroupDisabled }

    // Load the compiled stock module before resolving the history view's QML imports.
    Component.onCompleted: {
        stockModule.loadModule();
        stock.setSource("StockHistory.qml", {
            appletInterface: root,
            notificationSettings: policy,
            historyModel: history,
            clearHistoryAction: clearHistory
        });
        Plasmoid.setInternalAction("configure", configureAction);
    }
    MouseArea {
        id: trigger
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        onClicked: mouse => {
            if (mouse.button === Qt.MiddleButton)
                stock.item.toggleDoNotDisturb();
            else if (mouse.button === Qt.LeftButton)
                root.toggleHistory();
        }
        Kirigami.Icon { anchors.fill: parent; source: Plasmoid.icon }
    }

    NM.Notifications {
        id: popups
        showExpired: false
        showDismissed: false
        showAddedDuringInhibition: false
        showJobs: false
        blacklistedDesktopEntries: policy.popupBlacklistedApplications
        blacklistedNotifyRcNames: policy.popupBlacklistedServices
        whitelistedDesktopEntries: root.inhibited ? policy.doNotDisturbPopupWhitelistedApplications : []
        whitelistedNotifyRcNames: root.inhibited ? policy.doNotDisturbPopupWhitelistedServices : []
        sortMode: NM.Notifications.SortByTypeAndUrgency
        sortOrder: Qt.AscendingOrder
        groupMode: NM.Notifications.GroupDisabled
        window: root.anchorItem?.Window.window || null
        limit: Math.max(1, Math.ceil(root.workArea.height / (Kirigami.Units.gridUnit * 4)))
        urgencies: (!root.inhibited || policy.criticalPopupsInDoNotDisturbMode ? NM.Notifications.CriticalUrgency : 0)
            | (!root.inhibited ? NM.Notifications.NormalUrgency : 0)
            | (!root.inhibited && policy.lowPriorityPopups ? NM.Notifications.LowUrgency : 0)
        onShowNotificationsRequested: if (!historyPopup.visible) root.toggleHistory()
    }

    NM.Notifications {
        id: history
        showExpired: true
        showDismissed: true
        showJobs: policy.jobsInNotifications
        sortMode: NM.Notifications.SortByDate
        groupMode: NM.Notifications.GroupApplicationsFlat
        groupLimit: 2
        expandUnread: true
        ignoreBlacklistDuringInhibition: true
        blacklistedDesktopEntries: policy.historyBlacklistedApplications
        blacklistedNotifyRcNames: policy.historyBlacklistedServices
        urgencies: NM.Notifications.CriticalUrgency | NM.Notifications.NormalUrgency
            | (policy.lowPriorityHistory ? NM.Notifications.LowUrgency : 0)
        window: historyPopup
    }

    Instantiator {
        id: balloons
        model: popups
        delegate: Balloon {
            required property var model
            required property int index
            entry: model
            row: index
            source: popups
            settings: policy
            focusControl: balloonFocus
            tasks: taskModel
            availableHeight: Math.max(54, Math.floor(root.workArea.height * 0.8))
            critical: model.urgency === NM.Notifications.CriticalUrgency
                || (model.urgency === NM.Notifications.NormalUrgency && !policy.inhibitNotificationsWhenFullscreen)
            onHeightChanged: Qt.callLater(root.positionPopups)
        }
        onObjectAdded: (index, object) => {
            const popup = object as Balloon;
            const row = popups.index(index, 0);
            if (root.inhibited)
                popup.entry.wasAddedDuringInhibition = false;
            if (popup.entry.type === NM.Notifications.NotificationType && popup.entry.desktopEntry && !popup.entry.notifyRcName) {
                policy.registerKnownApplication(popup.entry.desktopEntry);
                policy.save();
            }
            popups.stopTimeout(row);
            popups.playSoundHint(row);
            Qt.callLater(root.positionPopups);
        }
        onObjectRemoved: (index, object) => {
            const popup = object as Balloon;
            const id = Number(popup.notificationId);
            if (Number.isInteger(id) && id > 0)
                popups.startTimeout(id);
            Qt.callLater(root.positionPopups);
        }
    }

    Timer {
        interval: 100
        repeat: true
        running: balloons.count > 0
        onTriggered: root.positionPopups()
    }

    function positionPopups() {
        const area = workArea;
        if (!balloonAnchor?.Window.window || area.width <= 0 || area.height <= 0)
            return;

        const anchor = balloonAnchor.mapToGlobal(balloonAnchor.width / 2, balloonAnchor.height / 2);
        const pos = policy.popupPosition;
        const above = anchored ? anchor.y >= area.y + area.height / 2 : pos >= NM.Settings.BottomLeft;
        const towardsLeft = pos === NM.Settings.TopLeft || pos === NM.Settings.BottomLeft;
        const centered = pos === NM.Settings.TopCenter || pos === NM.Settings.BottomCenter;
        let edge = above ? area.y + area.height : area.y;
        if (!anchored)
            edge += above ? -2 * Kirigami.Units.gridUnit : 2 * Kirigami.Units.gridUnit;
        for (let i = 0; i < balloons.count; ++i) {
            const p = balloons.objectAt(i) as Balloon;
            if (!p)
                continue;
            p.tail = anchored && i === 0;
            p.tailAtBottom = above;
            const w = p.width || 272;
            const preferredX = anchored ? anchor.x - 235 : centered ? area.x + (area.width - w) / 2
                : towardsLeft ? area.x + 2 * Kirigami.Units.gridUnit : area.x + area.width - w - 2 * Kirigami.Units.gridUnit;
            p.x = Math.round(Math.max(area.x, Math.min(preferredX, area.x + area.width - w)));
            p.tailOffset = Math.round(Math.max(15, Math.min(w - 15, anchor.x - p.x)));
            p.y = Math.round(above ? edge - p.height : edge);
            p.visible = i === 0 || (above ? p.y > area.y + area.height * 0.2 : p.y + p.height < area.y + area.height * 0.8);
            edge += above ? -p.height - 4 : p.height + 4;
        }
    }

    PlasmaCore.Dialog {
        id: historyPopup
        visualParent: root.anchorItem
        location: Plasmoid.location
        type: PlasmaCore.Dialog.AppletPopup
        backgroundHints: PlasmaCore.Dialog.SolidBackground
        hideOnWindowDeactivate: true
        visible: false
        onVisibleChanged: {
            root.expanded = visible;
            if (!visible) {
                history.lastRead = undefined;
                history.collapseAllGroups();
            }
        }
        mainItem: Item {
            implicitWidth: 18 * Kirigami.Units.gridUnit
            implicitHeight: 24 * Kirigami.Units.gridUnit
            Keys.onEscapePressed: historyPopup.close()
            Loader {
                id: stock
                anchors.fill: parent
                onStatusChanged: if (status === Loader.Error) console.error("Cannot load the stock Plasma notification history")
            }
        }
    }

    PlasmaCore.Action {
        id: configureAction
        text: qsTr("Configure Notifications…")
        icon.name: "configure"
        visible: KConfig.KAuthorized.authorizeControlModule("kcm_notifications")
        onTriggered: KCMUtils.KCMLauncher.openSystemSettings("kcm_notifications")
    }
    Plasmoid.contextualActions: [PlasmaCore.Action {
        id: clearHistory
        text: qsTr("Clear All Notifications")
        icon.name: "edit-clear-history"
        visible: history.expiredNotificationsCount > 0
        onTriggered: root.clearNotificationHistoryAndShowOsd()
    }]
}
