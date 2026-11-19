pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Templates as T
import "../../../../../win7-classic/primitives2" as Classic

T.ScrollBar {
    id: bar
    required property ListView list
    width: 16
    topPadding: 16
    bottomPadding: 16
    minimumSize: 14 / Math.max(14, availableHeight)
    focusPolicy: Qt.NoFocus
    wheelEnabled: true
    stepSize: 1 / Math.max(1, list.count)
    onPressedChanged: if (pressed) list.cancelFlick()

    function page(direction: int): void {
        list.cancelFlick();
        position = Math.max(0, Math.min(1 - size, position + direction * size));
    }

    background: Image {
        y: bar.topPadding
        width: bar.width
        height: bar.availableHeight
        source: "assets/program-scroll-track.png"
        fillMode: Image.Tile
        horizontalAlignment: Image.AlignLeft
        verticalAlignment: Image.AlignTop
        smooth: false
    }
    contentItem: Classic.Raster {
        id: thumb
        fill: Classic.Palette.face
        edge: Classic.Raster.Raised
    }

    MouseArea {
        x: 0; y: bar.topPadding
        width: bar.width; height: bar.availableHeight
        onPressed: mouse => {
            // Let Qt drag the actual thumb, but page instead of jumping to a track click.
            const y = mouse.y + bar.topPadding;
            if (y >= thumb.y && y < thumb.y + thumb.height)
                mouse.accepted = false;
            else
                bar.page(y < thumb.y ? -1 : 1);
        }
    }

    component ArrowButton: T.Button {
        id: arrow
        required property bool up
        width: bar.width; height: 16
        focusPolicy: Qt.NoFocus
        autoRepeat: true
        Accessible.name: up ? qsTr("Scroll up") : qsTr("Scroll down")
        onClicked: {
            bar.list.cancelFlick();
            if (up) bar.decrease();
            else bar.increase();
        }
        background: Classic.Raster {
            fill: Classic.Palette.face
            edge: arrow.down ? Classic.Raster.Sunken : Classic.Raster.Raised
            Image {
                x: 4 + (arrow.down ? 1 : 0)
                y: 6 + (arrow.down ? 1 : 0)
                source: arrow.up ? "assets/program-scroll-up.png" : "assets/program-scroll-down.png"
                smooth: false
            }
        }
    }
    ArrowButton { up: true }
    ArrowButton { up: false; y: bar.height - height }
}
