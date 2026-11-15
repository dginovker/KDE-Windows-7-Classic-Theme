import QtQuick

// Win32 DrawEdge as Classic draws buttons: two 1px rings, light top-left and dark bottom-right when raised, reversed when sunken.
Item {
    property bool sunken: false
    property color fill: "#d4d0c8"
    readonly property color outerTopLeft: sunken ? "#404040" : "#ffffff"
    readonly property color outerBottomRight: sunken ? "#ffffff" : "#404040"
    readonly property color innerTopLeft: sunken ? "#808080" : "#d4d0c8"
    readonly property color innerBottomRight: sunken ? "#d4d0c8" : "#808080"

    Rectangle { anchors.fill: parent; color: parent.fill }
    Rectangle { x: 1; y: 1; width: parent.width - 3; height: 1; color: innerTopLeft }
    Rectangle { x: 1; y: 1; width: 1; height: parent.height - 3; color: innerTopLeft }
    Rectangle { x: 1; y: parent.height - 2; width: parent.width - 2; height: 1; color: innerBottomRight }
    Rectangle { x: parent.width - 2; y: 1; width: 1; height: parent.height - 2; color: innerBottomRight }
    Rectangle { x: 0; y: 0; width: parent.width - 1; height: 1; color: outerTopLeft }
    Rectangle { x: 0; y: 0; width: 1; height: parent.height - 1; color: outerTopLeft }
    Rectangle { x: 0; y: parent.height - 1; width: parent.width; height: 1; color: outerBottomRight }
    Rectangle { x: parent.width - 1; y: 0; width: 1; height: parent.height; color: outerBottomRight }
}
