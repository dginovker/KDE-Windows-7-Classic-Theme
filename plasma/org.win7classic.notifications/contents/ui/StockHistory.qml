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
    readonly property bool hasAnchor: !!appletInterface?.compactRepresentationItem
    onHasAnchorChanged: {
        if (hasAnchor)
            Stock.Globals.adopt(appletInterface);
        else
            Stock.Globals.forget(appletInterface);
    }

    Component.onCompleted: {
        // Use KDE's unmodified history, DND, and shortcuts, but only one toast renderer.
        Stock.Globals.popupInstantiator.active = false;
    }
    Component.onDestruction: Stock.Globals.forget(history.appletInterface)
}
