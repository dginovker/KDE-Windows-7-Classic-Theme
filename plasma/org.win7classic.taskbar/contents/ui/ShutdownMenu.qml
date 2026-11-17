import QtQuick
import org.kde.plasma.core as PlasmaCore
import "../../../../../win7-classic/primitives2" as Classic

// Geometry is the 109x142 popup in w7-shutdown-menu.png, excluding its compositor shadow (#30).
PlasmaCore.Dialog {
    id: menu
    required property Item anchor
    required property var session
    required property bool ready
    required property bool switchUserSupported
    property int current: -1
    property bool returnToStart: false
    readonly property var actions: [
        {label: "Switch user", capability: "canSwitchUser", y: 3},
        {label: "Log off", capability: "canLogout", y: 23},
        {label: "Lock", capability: "canLock", y: 43},
        {label: "Restart", capability: "canReboot", y: 71},
        {label: "Sleep", capability: "canSuspend", y: 99},
        {label: "Hibernate", capability: "canHibernate", y: 119}
    ]
    signal chosen(int index)
    signal dismissed(bool returnToStart)
    type: PlasmaCore.Dialog.PopupMenu
    flags: Qt.WindowStaysOnTopHint
    backgroundHints: PlasmaCore.Dialog.NoBackground
    hideOnWindowDeactivate: true
    location: PlasmaCore.Types.Floating
    onVisibleChanged: if (!visible) dismissed(returnToStart)

    function available(index) {
        return ready && session[actions[index].capability] && (index !== 0 || (switchUserSupported && session.canLock));
    }
    function open() {
        const corner = anchor.mapToGlobal(anchor.width - 3, anchor.height + 3);
        x = corner.x;
        y = corner.y - body.height;
        current = -1;
        returnToStart = false;
        visible = true;
        requestActivate();
        body.forceActiveFocus();
    }
    function back() { returnToStart = true; visible = false; }
    function move(step) {
        for (let i = 1; i <= actions.length; ++i) {
            const next = (current + step * i + actions.length * 2) % actions.length;
            if (available(next)) { current = next; return; }
        }
    }
    function trigger(index) {
        if (index < 0 || !available(index))
            return;
        visible = false;
        chosen(index);
    }

    mainItem: Classic.Raster {
        id: body
        width: 109; height: 142
        fill: Classic.Palette.face
        edge: Classic.Raster.Raised
        focus: true
        Keys.onEscapePressed: menu.back()
        Keys.onLeftPressed: menu.back()
        Keys.onDownPressed: menu.move(1)
        Keys.onUpPressed: { if (menu.current < 0) menu.current = 0; menu.move(-1); }
        Keys.onReturnPressed: menu.trigger(menu.current)
        Keys.onEnterPressed: menu.trigger(menu.current)
        Keys.onSpacePressed: menu.trigger(menu.current)
        Classic.Raster { x: 5; y: 66; width: 99; height: 2; edge: Classic.Raster.Etched; flags: Classic.Raster.Top }
        Classic.Raster { x: 5; y: 94; width: 99; height: 2; edge: Classic.Raster.Etched; flags: Classic.Raster.Top }
        Repeater {
            model: menu.actions
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                readonly property bool available: menu.available(index)
                readonly property bool selected: menu.current === index && available
                x: 3; y: modelData.y; width: 103; height: 20
                color: selected ? Classic.Palette.selection : "transparent"
                Text {
                    x: 26; y: 1; height: 20
                    visible: !row.available
                    text: row.modelData.label
                    font.family: "Tahoma"; font.pixelSize: 11
                    renderType: Text.NativeRendering
                    verticalAlignment: Text.AlignVCenter
                    color: Classic.Palette.highlight3D
                }
                Text {
                    x: 25; height: 20
                    text: row.modelData.label
                    font.family: "Tahoma"; font.pixelSize: 11
                    renderType: Text.NativeRendering
                    verticalAlignment: Text.AlignVCenter
                    color: !row.available ? Classic.Palette.grayText : row.selected ? Classic.Palette.selectionText : Classic.Palette.text
                }
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: menu.current = row.available ? row.index : -1
                    onExited: if (menu.current === row.index) menu.current = -1
                    onClicked: menu.trigger(row.index)
                }
            }
        }
    }
}
