// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import plasma.applet.org.kde.plasma.notifications as Stock

Stock.FullRepresentation {
    id: history

    function toggleDoNotDisturb() { Stock.Globals.toggleDoNotDisturbMode(); }
    function hideInhibitionSummary() { Stock.Globals.popupNotificationsModel.hideInhibitionSummary(); }
    function showHistoryCleaned() { Stock.Globals.shortcuts.showNotificationsHistoryCleaned(); }
    readonly property bool inhibited: Stock.Globals.inhibited

    anchors.fill: parent
    // KDE's stock clear-history shortcut and coordinator refer to the active view's anchor.
    QtObject {
        id: coordinatorView
        readonly property Item compactRepresentationItem: history.appletInterface.anchorItem
        function clearNotificationHistoryAndShowOsd() { history.appletInterface.clearNotificationHistoryAndShowOsd(); }
    }

    Component.onCompleted: {
        // Use KDE's unmodified history, DND, and shortcuts, but only one toast renderer.
        Stock.Globals.popupInstantiator.active = false;
        Stock.Globals.plasmoidItem = coordinatorView;
    }
    Component.onDestruction: Stock.Globals.plasmoidItem = null
}
