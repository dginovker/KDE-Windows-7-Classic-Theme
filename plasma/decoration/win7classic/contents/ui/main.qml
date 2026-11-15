import QtQuick
import org.kde.kwin.decoration

// Windows 7 Classic frame, measured from reference/screenshots/w7-{taskbar,inactive,maximized}.png:
// a 4px raised edge, an 18px caption (solid under the icon, gradient up to the buttons, solid under them)
// and a 1px face row above the client. Maximized windows lose the frame and keep 2px caption margins.
Decoration {
    id: root
    alpha: false
    readonly property bool maximized: decoration.client.maximized
    readonly property bool active: decoration.client.active
    readonly property color dark: active ? "#0a246a" : "#808080"
    readonly property color light: active ? "#a6caf0" : "#c0c0c0"
    readonly property int edge: maximized ? 0 : 4
    readonly property int margin: maximized ? 2 : 6

    DecorationOptions { id: options; deco: decoration }

    Component.onCompleted: {
        borders.setBorders(4);
        borders.setTitle(23);
        maximizedBorders.setBorders(0);
        maximizedBorders.setTitle(19);
    }

    Rectangle { anchors.fill: parent; color: "#d4d0c8" }

    // Raised outer edge (DrawEdge EDGE_RAISED): face/white rings top-left, dark/gray rings bottom-right.
    Item {
        anchors.fill: parent
        visible: !root.maximized
        Rectangle { x: 1; y: 1; width: parent.width - 3; height: 1; color: "#ffffff" }
        Rectangle { x: 1; y: 1; width: 1; height: parent.height - 3; color: "#ffffff" }
        Rectangle { x: parent.width - 2; y: 1; width: 1; height: parent.height - 2; color: "#808080" }
        Rectangle { x: 1; y: parent.height - 2; width: parent.width - 2; height: 1; color: "#808080" }
        Rectangle { x: parent.width - 1; y: 0; width: 1; height: parent.height; color: "#404040" }
        Rectangle { x: 0; y: parent.height - 1; width: parent.width; height: 1; color: "#404040" }
    }

    Item {
        id: caption
        x: root.edge; y: root.edge
        width: root.width - 2 * root.edge
        height: 18
        Rectangle { width: 20; height: parent.height; color: root.dark }
        Rectangle {
            x: 20; width: parent.width - 20 - 54; height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: root.dark }
                GradientStop { position: 1; color: root.light }
            }
        }
        Rectangle { x: parent.width - 54; width: 54; height: parent.height; color: root.light }
        Component.onCompleted: decoration.installTitleItem(caption)
    }

    Buttons {
        id: leftButtons
        x: root.margin; y: root.edge + 1
        types: options.titleButtonsLeft
    }
    Text {
        x: leftButtons.x + leftButtons.width + 2
        y: root.edge
        width: rightButtons.x - x
        height: 18
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: decoration.client.caption
        textFormat: Text.PlainText
        font: options.titleFont
        color: root.active ? "#ffffff" : "#d4d0c8"
        renderType: Text.NativeRendering
    }
    Buttons {
        id: rightButtons
        x: root.width - root.margin - width; y: root.edge + 2
        types: options.titleButtonsRight
    }

    // Laid out here rather than with KWin's ButtonGroup: KWin 6.8 reports the "_" spacer from kwinrc as
    // DecorationButtonNone (0), which ButtonGroup doesn't recognise as DecorationButtonExplicitSpacer.
    component Buttons: Row {
        property var types: []
        Repeater {
            model: parent.types
            delegate: Loader {
                required property int modelData
                sourceComponent: modelData === DecorationOptions.DecorationButtonMenu ? menu
                    : modelData === DecorationOptions.DecorationButtonNone ? spacer
                    : [DecorationOptions.DecorationButtonMinimize, DecorationOptions.DecorationButtonMaximizeRestore,
                       DecorationOptions.DecorationButtonClose].indexOf(modelData) >= 0 ? caption : null
                Component { id: menu; MenuButton { width: 16; height: 16 } }
                Component { id: spacer; Item { width: 2; height: 14 } }
                Component { id: caption; CaptionButton { buttonType: modelData } }
            }
        }
    }
}
