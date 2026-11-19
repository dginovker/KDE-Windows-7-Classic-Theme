import QtQuick
import QtQuick.Window
import "../../../../../win7-classic/primitives2" as Classic
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

// The stock system tray sits inside this single sunken outer edge, not a two-ring client edge.
PlasmoidItem {
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    fullRepresentation: Item {
        Layout.minimumWidth: 7
        Layout.maximumWidth: 7
        Layout.fillHeight: true
        id: area
        property point origin: Qt.point(0, 0)
        function syncOrigin() { origin = mapToItem(null, 0, 0) }
        Component.onCompleted: Qt.callLater(syncOrigin)
        Connections {
            target: area.Window.window
            function onAfterAnimating() { area.syncOrigin() }
        }
        Classic.Raster {
            x: 0; y: 4 - area.origin.y
            width: area.Window.window ? area.Window.window.width - area.origin.x - 2 : 0
            height: area.Window.window ? Math.max(0, Math.min(38, area.Window.window.height - 6)) : 0
            edge: Classic.Raster.SunkenOuter
        }
    }
}
