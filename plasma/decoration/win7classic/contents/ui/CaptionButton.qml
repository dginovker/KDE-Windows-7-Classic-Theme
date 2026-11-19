import QtQuick
import "../../../../../win7-classic/primitives2" as Classic
import org.kde.kwin.decoration

// DrawFrameControl caption button: 16x14 bevel, sunken with the glyph shifted 1px while pressed.
// Glyph rectangles are measured from reference/screenshots/w7-{taskbar,maximized}.png.
// Not a DecorationButton: KWin sends no moves while a button is held, so MouseArea's clicked fires even when the
// pointer is released elsewhere. Windows cancels the action in that case, so the release position is checked here.
Item {
    id: button
    required property int buttonType
    width: 16
    height: 14
    readonly property bool contextHelp: buttonType === DecorationOptions.DecorationButtonQuickHelp
    enabled: buttonType === DecorationOptions.DecorationButtonClose ? decoration.client.closeable
        : buttonType === DecorationOptions.DecorationButtonMinimize ? decoration.client.minimizeable
        : contextHelp ? decoration.client.providesContextHelp : decoration.client.maximizeable
    readonly property bool sunken: mouse.pressed && frame.pointerInside
    Classic.Raster {
        id: frame
        eventSource: decoration
        anchors.fill: parent
        button: true
        pressed: button.sunken
        disabled: !button.enabled
        glyph: button.contextHelp ? 0
            : button.buttonType === DecorationOptions.DecorationButtonMinimize ? Classic.Raster.Minimize
            : button.buttonType === DecorationOptions.DecorationButtonClose ? Classic.Raster.Close
            : decoration.client.maximized ? Classic.Raster.Restore : Classic.Raster.Maximize
    }

    Text {
        visible: button.contextHelp
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: button.sunken ? 1 : 0
        anchors.verticalCenterOffset: button.sunken ? 1 : 0
        text: "?"
        color: Classic.Palette.text
        font.pixelSize: 11
        font.bold: true
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: button.contextHelp ? Qt.LeftButton : Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
        onReleased: (event) => {
            if (event.x < 0 || event.y < 0 || event.x >= width || event.y >= height)
                return;
            if (button.buttonType === DecorationOptions.DecorationButtonClose)
                decoration.requestClose();
            else if (button.buttonType === DecorationOptions.DecorationButtonMinimize)
                decoration.requestMinimize();
            else if (button.contextHelp)
                decoration.requestContextHelp();
            else
                decoration.requestToggleMaximization(event.button);
        }
    }
}
