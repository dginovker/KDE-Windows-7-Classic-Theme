import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

// Draws the notification area's 1px sunken frame from here to the panel's right end, so the
// stock system tray placed after this applet sits inside it. org.win7classic.clock closes the frame.
PlasmoidItem {
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    fullRepresentation: Item {
        Layout.minimumWidth: 7
        Layout.maximumWidth: 7
        Layout.fillHeight: true
        id: area
        property real originY: 0
        Component.onCompleted: Qt.callLater(() => originY = mapToItem(null, 0, 0).y)
        // Panel-window rows 4 and 41 (screen 760 and 797); the clock applet trims the overflow on the right.
        Rectangle { x: 0; y: 4 - area.originY; width: 10000; height: 1; color: "#808080" }
        Rectangle { x: 0; y: 4 - area.originY; width: 1; height: 37; color: "#808080" }
        Rectangle { x: 0; y: 41 - area.originY; width: 10000; height: 1; color: "#ffffff" }
    }
}
