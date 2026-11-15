import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid

// A magenta block showing its own setting, so the test can find it on screen and see its config survived.
PlasmoidItem {
    preferredRepresentation: fullRepresentation
    fullRepresentation: Rectangle {
        Layout.minimumWidth: 70
        Layout.maximumWidth: 70
        Layout.fillHeight: true
        color: "#ff00ff"
        Text { anchors.centerIn: parent; text: Plasmoid.configuration.text; color: "black" }
    }
}
