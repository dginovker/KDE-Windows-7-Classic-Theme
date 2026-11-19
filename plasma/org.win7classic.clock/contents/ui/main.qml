import QtQuick
import "../../../../../win7-classic/primitives2" as Classic
import QtQuick.Layouts
import QtQuick.Templates as T
import QtQuick.Window
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.clock as PlasmaClock
import org.kde.kirigami as Kirigami
import org.kde.plasma.workspace.dbus as DBus

// Must be the last applet: its right padding reserves the notification frame termination.
// Positions are relative to the panel window's right edge (reference: frame ends 3px from it), not the applet.
PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    PlasmaClock.Clock { id: clock; trackSeconds: true }
    Plasmoid.onActivated: toggleCalendar()

    function toggleCalendar() {
        if (calendar.visible)
            calendar.close();
        else if (root.Window.window)
            calendar.open();
    }

    CalendarPopup {
        id: calendar
        now: clock.dateTime
        transientParent: root.Window.window
        x: root.Screen.virtualX + root.Screen.width - width
        y: transientParent ? transientParent.y - height : 0
    }

    fullRepresentation: Item {
        id: area
        Layout.minimumWidth: 80
        Layout.maximumWidth: 80
        Layout.fillHeight: true
        property point origin: Qt.point(0, 0)
        // Window-x of the panel's right edge, in this item's coordinates.
        readonly property real panelRight: (Window.window ? Window.window.width : 0) - origin.x
        function syncOrigin() { origin = mapToItem(null, 0, 0) }
        Component.onCompleted: Qt.callLater(syncOrigin)
        onWidthChanged: Qt.callLater(syncOrigin)
        Connections { target: area.Window.window; function onAfterAnimating() { area.syncOrigin() } }

        // An unfocusable panel does not deactivate the popup when clicked. Observe its
        // taps passively, without taking the neighboring widgets' pointer events.
        TapHandler {
            id: panelTap
            parent: area.Window.window ? area.Window.window.contentItem : area
            enabled: calendar.visible
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onTapped: (point, button) => {
                if (button !== Qt.LeftButton || !trigger.contains(trigger.mapFromItem(null, point.scenePosition)))
                    calendar.close();
            }
        }

        Column {
            x: area.panelRight - 84; width: 66
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 1
            spacing: 1
            Repeater {
                model: [Qt.formatTime(clock.dateTime, Qt.locale().timeFormat(Locale.ShortFormat)),
                        // Windows shows a four-digit year where Qt's short locale format has two.
                        Qt.formatDate(calendar.localDate, Qt.locale().dateFormat(Locale.ShortFormat).replace(/\byy\b/, "yyyy"))]
                delegate: Text {
                    required property string modelData
                    width: 66
                    horizontalAlignment: Text.AlignHCenter
                    text: modelData
                    font.family: "Tahoma"; font.pixelSize: 11
                    color: Classic.Palette.text
                    renderType: Text.NativeRendering
                }
            }
        }
        T.AbstractButton {
            id: trigger
            x: Math.max(0, area.panelRight - 84)
            width: Math.max(0, area.panelRight - 19 - x)
            height: area.height
            focusPolicy: Qt.TabFocus
            Accessible.name: qsTr("Date and time calendar")
            Keys.onReturnPressed: root.toggleCalendar()
            Keys.onEnterPressed: root.toggleCalendar()
            onClicked: root.toggleCalendar()
            background: Classic.Raster {
                anchors.fill: parent
                anchors.margins: 3
                focused: trigger.visualFocus
            }
        }
        Kirigami.Icon {
            x: area.panelRight - 19
            y: area.Window.window ? Math.min(15, Math.floor((area.Window.window.height - height) / 2) + 1) - area.origin.y : 0
            width: 16; height: 16
            source: "user-desktop"
            MouseArea {
                anchors.fill: parent
                onClicked: DBus.SessionBus.asyncCall({ service: "org.kde.kglobalaccel", path: "/component/kwin", iface: "org.kde.kglobalaccel.Component", member: "invokeShortcut", arguments: [new DBus.string("Show Desktop")], signature: "(s)" })
            }
        }
    }
}
