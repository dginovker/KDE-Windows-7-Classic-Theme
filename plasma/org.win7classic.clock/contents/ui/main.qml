import QtQuick
import "../../../../../win7-classic/primitives2" as Classic
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import org.kde.plasma.workspace.dbus as DBus

// Must be the last applet: its right padding reserves the notification frame termination.
// Positions are relative to the panel window's right edge (reference: frame ends 3px from it), not the applet.
PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    property date now: new Date()
    Timer { interval: 1000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.now = new Date() }

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

        Column {
            x: area.panelRight - 84; width: 66
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 1
            spacing: 1
            Repeater {
                model: [Qt.formatTime(root.now, Qt.locale().timeFormat(Locale.ShortFormat)),
                        // Windows shows a four-digit year where Qt's short locale format has two.
                        Qt.formatDate(root.now, Qt.locale().dateFormat(Locale.ShortFormat).replace(/\byy\b/, "yyyy"))]
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
        Kirigami.Icon {
            x: area.panelRight - 19; y: 15 - area.origin.y; width: 16; height: 16
            source: "user-desktop"
            MouseArea {
                anchors.fill: parent
                onClicked: DBus.SessionBus.asyncCall({ service: "org.kde.kglobalaccel", path: "/component/kwin", iface: "org.kde.kglobalaccel.Component", member: "invokeShortcut", arguments: [new DBus.string("Show Desktop")], signature: "(s)" })
            }
        }
    }
}
