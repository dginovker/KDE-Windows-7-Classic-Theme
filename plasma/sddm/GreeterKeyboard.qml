import QtQuick
import QtQuick.VirtualKeyboard

InputPanel {
    property bool available: false
    // A detached Qt Virtual Keyboard context never receives a focused input item.
    // Remember the connection so tabbing to the keyboard button doesn't hide it.
    readonly property bool hasInputItem: InputContext.inputItem != null
    onHasInputItemChanged: if (hasInputItem) available = true
    Component.onCompleted: if (hasInputItem) available = true
    visible: active
}
