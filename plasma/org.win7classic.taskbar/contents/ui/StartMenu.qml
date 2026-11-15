import QtCore
import QtQuick
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.coreaddons as KCoreAddons
import org.kde.plasma.private.kicker as Kicker
import org.kde.plasma.workspace.dbus as DBus

// The Windows 7 Classic Start menu. Coordinates are menu pixels measured from reference/screenshots/w7-menu*.png
// (menu origin = screen 0,295), so they can be compared one-to-one with the reference.
PlasmaCore.Dialog {
    id: menu
    required property Item applet
    property string view: "favorites"   // favorites | programs | search
    property var programsModel: null      // the folder shown in programs view; null = top level
    property var programsPath: []
    property int current: -1              // keyboard/hover selection in the left list
    // Windows drops Start's focus rectangle while the mouse hot-tracks a menu item (w7-menu-hover-*.png),
    // but not over All Programs/Back (w7-programs.png).
    readonly property bool hotTracking: favoritesHover.count > 0 || placesHover.count > 0

    readonly property color face: "#d4d0c8"
    readonly property color highlight: "#0a246a"
    readonly property font uiFont: Qt.font({ family: "Tahoma", pixelSize: 11 })

    type: PlasmaCore.Dialog.PopupMenu
    backgroundHints: PlasmaCore.Dialog.NoBackground
    flags: Qt.WindowStaysOnTopHint
    hideOnWindowDeactivate: true
    location: PlasmaCore.Types.Floating
    // Windows anchors the menu to the screen's bottom-left corner, directly above the taskbar.
    x: applet.Window.window ? applet.Window.window.x : 0
    y: applet.Window.window ? applet.Window.window.y - 461 : 0

    function open() {
        search.text = "";
        view = "favorites";
        programsModel = null;
        programsPath = [];
        current = -1;
        visible = true;
        requestActivate();
        search.forceActiveFocus();
    }
    function close() { visible = false; }
    function runCommand(service, path, iface, member, args, signature) {
        DBus.SessionBus.asyncCall({ service: service, path: path, iface: iface, member: member, arguments: args, signature: signature });
    }
    function openUrl(url) { Qt.openUrlExternally(url); close(); }
    function launch(model, row) {
        if (!model.trigger(row, "", null))
            throw new Error("win7-classic: Start menu could not launch row " + row + " of " + model);
        close();
    }

    mainItem: Item {
        id: root
        width: 405
        height: 461
        focus: true
        Keys.onEscapePressed: menu.close()
        QtObject { id: favoritesHover; property int count: 0 }
        QtObject { id: placesHover; property int count: 0 }

        Kicker.SimpleFavoritesModel {
            id: favorites
            favorites: Plasmoid.configuration.favorites
        }
        Kicker.RootModel {
            id: programs
            appletInterface: menu.applet
            flat: false
            sorted: true
            showSeparators: false
            showTopLevelItems: true
            showAllApps: false
            showRecentApps: false
            showRecentDocs: false
            showPowerSession: false
        }
        Kicker.RunnerModel {
            id: runner
            appletInterface: menu.applet
            mergeResults: false
            runners: ["krunner_services", "krunner_systemsettings"]
            query: search.text
        }
        KCoreAddons.KUser { id: user }


        Rectangle { anchors.fill: parent; color: menu.face }
        // DrawEdge EDGE_RAISED with Classic colors: ButtonLight/Highlight top-left, Shadow/DkShadow bottom-right.
        Rectangle { x: 1; y: 1; width: 402; height: 1; color: "#ffffff" }
        Rectangle { x: 1; y: 1; width: 1; height: 458; color: "#ffffff" }
        Rectangle { x: 403; y: 1; width: 1; height: 459; color: "#808080" }
        Rectangle { x: 1; y: 459; width: 403; height: 1; color: "#808080" }
        Rectangle { x: 404; y: 0; width: 1; height: 461; color: "#404040" }
        Rectangle { x: 0; y: 460; width: 405; height: 1; color: "#404040" }

        component Etch: Item {
            // A sunken 2px line: shadow row, then a highlight row starting one pixel in.
            height: 2
            Rectangle { width: parent.width; height: 1; color: "#808080" }
            Rectangle { y: 1; width: 1; height: 1; color: "#808080" }
            Rectangle { x: 1; y: 1; width: parent.width - 1; height: 1; color: "#ffffff" }
        }
        component Label: Text {
            font: menu.uiFont
            color: "black"
            renderType: Text.NativeRendering
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        component Triangle: Item {
            // Solid arrow 4 wide and 7 tall, pointing left or right.
            property bool pointsLeft: false
            property color color: "black"
            width: 4; height: 7
            Repeater {
                model: [1, 2, 3, 4, 3, 2, 1]
                delegate: Rectangle {
                    required property int modelData
                    required property int index
                    x: parent.pointsLeft ? 4 - modelData : 0
                    y: index; width: modelData; height: 1; color: parent.color
                }
            }
        }

        // ---------- favorites view: left column ----------
        Item {
            visible: menu.view === "favorites"
            anchors.fill: parent
            Repeater {
                model: favorites
                delegate: Item {
                    required property var model
                    required property int index
                    readonly property bool selected: menu.current === index
                    x: 9; y: 7 + 38 * index; width: 238; height: 36
                    Rectangle { anchors.fill: parent; color: menu.highlight; visible: parent.selected }
                    Kirigami.Icon { x: 2; y: 2; width: 32; height: 32; source: model.decoration; selected: parent.selected }
                    Label { x: 40; width: 196; height: 36; text: model.display; color: parent.selected ? "white" : "black" }
                    MouseArea {
                        anchors.fill: parent; hoverEnabled: true
                        onEntered: menu.current = index
                        onContainsMouseChanged: favoritesHover.count += containsMouse ? 1 : -1
                        onClicked: menu.launch(favorites, index)
                    }
                }
            }
        }

        // ---------- programs view: white list ----------
        Rectangle {
            visible: menu.view === "programs"
            x: 3; y: 3; width: 250; height: 378; color: "white"
            clip: true
            ListView {
                id: programList
                anchors.fill: parent; anchors.topMargin: 2
                model: menu.programsModel || programs
                boundsBehavior: Flickable.StopAtBounds
                delegate: Item {
                    required property var model
                    required property int index
                    readonly property bool selected: menu.current === index
                    width: 248; height: 18
                    Rectangle { x: 1; width: 246; height: 18; color: menu.highlight; visible: parent.selected }
                    Kirigami.Icon { x: 4; y: 1; width: 16; height: 16; source: model.decoration; selected: parent.selected }
                    Label { x: 24; width: 220; height: 18; text: model.display; color: parent.selected ? "white" : "black" }
                    MouseArea {
                        anchors.fill: parent; hoverEnabled: true
                        onEntered: menu.current = index
                        onClicked: menu.activateProgram(index)
                    }
                }
            }
        }
        // ---------- search view: results over both columns ----------
        Rectangle {
            visible: menu.view === "search"
            x: 7; y: 3; width: 395; height: 421; color: "white"
            clip: true
            Column {
                x: 0; y: 5; width: parent.width
                Repeater {
                    model: runner
                    delegate: Column {
                        id: group
                        required property int index
                        readonly property var matches: runner.modelForRow(index)
                        readonly property int offset: menu.searchOffset(index)
                        visible: matches && matches.count > 0
                        width: parent.width
                        Item {
                            width: parent.width; height: 22
                            Label {
                                id: header
                                x: 5; height: 22
                                // Windows names its groups "Programs" and "Control Panel"; KRunner names them after the runner.
                                text: (group.index === 0 ? "Programs" : "Control Panel") + " (" + (group.matches ? group.matches.count : 0) + ")"
                            }
                            Rectangle { x: header.x + header.implicitWidth + 7; y: 10; width: 390 - x; height: 1; color: "black" }
                        }
                        Repeater {
                            model: group.matches
                            delegate: Item {
                                required property var model
                                required property int index
                                readonly property bool selected: menu.current === group.offset + index
                                width: group.width; height: 22
                                Rectangle { x: 14; width: 379; height: 22; color: menu.highlight; visible: parent.selected }
                                Kirigami.Icon { x: 19; y: 3; width: 16; height: 16; source: model.decoration; selected: parent.selected }
                                Label { x: 37; width: 340; height: 22; text: model.display; color: parent.selected ? "white" : "black" }
                                MouseArea {
                                    anchors.fill: parent; hoverEnabled: true
                                    onEntered: menu.current = group.offset + index
                                    onClicked: menu.launch(group.matches, index)
                                }
                            }
                        }
                    }
                }
            }
        }

        // ---------- left column footer: separator and All Programs / Back ----------
        Etch {
            visible: menu.view !== "search"
            x: menu.view === "programs" ? 5 : 9; y: 392
            width: menu.view === "programs" ? 248 : 240
        }
        Item {
            visible: menu.view !== "search"
            x: 7; y: 394; width: 242; height: 30
            Rectangle { anchors.fill: parent; color: menu.highlight; visible: allPrograms.containsMouse }
            // Windows draws the Back arrow one pixel right of the All Programs arrow.
            Triangle { x: menu.view === "programs" ? 7 : 6; y: 11; pointsLeft: menu.view === "programs"; color: allPrograms.containsMouse ? "white" : "black" }
            Label { x: 38; height: 30; text: menu.view === "programs" ? "Back" : "All Programs"; color: allPrograms.containsMouse ? "white" : "black" }
            MouseArea {
                id: allPrograms
                anchors.fill: parent; hoverEnabled: true
                onClicked: menu.view === "programs" ? menu.programsBack() : menu.showPrograms()
            }
        }

        // ---------- right column ----------
        Item {
            visible: menu.view !== "search"
            anchors.fill: parent
            Rectangle { x: 253; y: 3; width: 1; height: 421; color: "#808080" }
            Rectangle { x: 254; y: 3; width: 1; height: 421; color: "#ffffff" }

            // User picture in a raised frame, where Windows shows the account picture.
            Item {
                x: 296; y: 7; width: 68; height: 64
                Rectangle { anchors.fill: parent; color: "#ffffff"; radius: 3 }
                Rectangle { x: 1; y: 1; width: 66; height: 62; radius: 3; color: "#a0a0a0" }
                Kirigami.Icon { x: 6; y: 4; width: 56; height: 56; source: user.faceIconUrl.toString() ? user.faceIconUrl : "user-identity" }
            }

            Repeater {
                model: [
                    { label: user.fullName || user.loginName, y: 78, url: "file://" + StandardPaths.writableLocation(StandardPaths.HomeLocation) },
                    { label: "Documents", y: 112, url: StandardPaths.writableLocation(StandardPaths.DocumentsLocation) },
                    { label: "Pictures", y: 146, url: StandardPaths.writableLocation(StandardPaths.PicturesLocation) },
                    { label: "Music", y: 180, url: StandardPaths.writableLocation(StandardPaths.MusicLocation) },
                    { label: "Games", y: 217, run: "games" },
                    { label: "Computer", y: 251, url: "file:///" },
                    { label: "Control Panel", y: 288, run: "systemsettings" },
                    { label: "Devices and Printers", y: 322, run: "kcm_printer_manager" },
                    { label: "Default Programs", y: 356, run: "kcm_componentchooser" },
                    { label: "Help and Support", y: 390, url: "help:/" },
                ]
                delegate: Item {
                    required property var modelData
                    x: 259; y: modelData.y; width: 143; height: 32
                    Rectangle { anchors.fill: parent; color: menu.highlight; visible: place.containsMouse }
                    Label { x: 8; width: 132; height: 32; text: modelData.label; color: place.containsMouse ? "white" : "black" }
                    MouseArea {
                        id: place
                        anchors.fill: parent; hoverEnabled: true
                        onContainsMouseChanged: placesHover.count += containsMouse ? 1 : -1
                        onClicked: modelData.url ? menu.openUrl(modelData.url) : menu.runApplication(modelData.run)
                    }
                }
            }
            Etch { x: 259; y: 214; width: 143 }
            Etch { x: 259; y: 285; width: 143 }
        }

        // ---------- bottom: separator, search box, Shut down ----------
        Rectangle { x: 3; y: 424; width: 399; height: 1; color: "#808080" }
        Rectangle { x: 3; y: 425; width: 399; height: 1; color: "#ffffff" }

        Item {
            id: searchBox
            // Windows widens the box by 3px while searching, when the magnifier turns into a clear button.
            x: 7; y: 428; width: menu.view === "search" ? 224 : 221; height: 23
            // DrawEdge EDGE_SUNKEN around a white field.
            Rectangle { anchors.fill: parent; color: "#ffffff" }
            Rectangle { width: parent.width - 1; height: 1; color: "#808080" }
            Rectangle { width: 1; height: 22; color: "#808080" }
            Rectangle { x: 1; y: 1; width: parent.width - 3; height: 1; color: "#404040" }
            Rectangle { x: 1; y: 1; width: 1; height: 20; color: "#404040" }
            Rectangle { x: 1; y: 21; width: parent.width - 2; height: 1; color: menu.face }
            Rectangle { x: parent.width - 2; y: 1; width: 1; height: 21; color: menu.face }
            Rectangle { x: parent.width - 1; width: 1; height: 23; color: "#ffffff" }
            Rectangle { y: 22; width: parent.width; height: 1; color: "#ffffff" }
            TextInput {
                id: search
                x: 5; y: 2; width: searchBox.width - 9; height: 19
                verticalAlignment: TextInput.AlignVCenter
                font: menu.uiFont
                color: "black"
                renderType: Text.NativeRendering
                clip: true
                focus: true
                onTextChanged: {
                    menu.current = text.length ? 0 : -1;
                    menu.view = text.length ? "search" : "favorites";
                }
                Keys.onUpPressed: menu.move(-1)
                Keys.onDownPressed: menu.move(1)
                Keys.onReturnPressed: menu.activateCurrent()
                Keys.onEnterPressed: menu.activateCurrent()
                Label {
                    visible: !search.text.length
                    height: parent.height
                    text: "Search programs and files"
                }
            }
        }
        Kirigami.Icon {
            x: searchBox.x + searchBox.width + 2; y: 431; width: 16; height: 16
            source: search.text.length ? "edit-clear" : "search"
            MouseArea { anchors.fill: parent; onClicked: search.text = "" }
        }

        // Shut down: one raised button with a separate arrow part, like Windows' split button.
        Item {
            id: shutdown
            x: 257; y: 428; width: 86; height: 23
            Rectangle { anchors.fill: parent; color: menu.face }
            Rectangle { width: 85; height: 1; color: "#ffffff" }
            Rectangle { width: 1; height: 22; color: "#ffffff" }
            Rectangle { x: 84; y: 1; width: 1; height: 21; color: "#808080" }
            Rectangle { x: 1; y: 21; width: 84; height: 1; color: "#808080" }
            Rectangle { x: 85; width: 1; height: 23; color: "#404040" }
            Rectangle { y: 22; width: 86; height: 1; color: "#404040" }
            Rectangle { x: 71; y: 1; width: 1; height: 20; color: "#808080" }
            Rectangle { x: 72; width: 1; height: 22; color: "#ffffff" }
            Label { x: 1; width: 70; height: 22; horizontalAlignment: Text.AlignHCenter; text: "Shut down" }
            Triangle { x: 77; y: 7 }
            MouseArea {
                x: 0; width: 71; height: 23
                // KDE's confirmation dialog rather than an immediate power-off: unsaved work must never be lost to a misclick.
                onClicked: { menu.close(); menu.runCommand("org.kde.LogoutPrompt", "/LogoutPrompt", "org.kde.LogoutPrompt", "promptShutDown", [], "()"); }
            }
            MouseArea {
                x: 72; width: 14; height: 23
                onClicked: { menu.close(); menu.runCommand("org.kde.LogoutPrompt", "/LogoutPrompt", "org.kde.LogoutPrompt", "promptAll", [], "()"); }
            }
        }
    }

    // ---------- behaviour ----------
    function runApplication(id) {
        close();
        if (id === "games")
            Qt.openUrlExternally("applications:");
        else
            runCommand("org.kde.krunner", "/App", "org.kde.krunner.App", "query", [new DBus.string(id)], "(s)");
    }
    function showPrograms() {
        view = "programs";
        programsModel = null;
        programsPath = [];
        current = -1;
    }
    function programsBack() {
        if (programsPath.length) {
            programsPath = programsPath.slice(0, -1);
            programsModel = programsPath.length ? programsPath[programsPath.length - 1] : null;
        } else {
            view = "favorites";
        }
        current = -1;
    }
    function activateProgram(row) {
        const model = programsModel || programs;
        const child = model.modelForRow(row);
        if (child && child.count !== undefined) {
            programsPath = programsPath.concat([child]);
            programsModel = child;
            current = -1;
        } else {
            launch(model, row);
        }
    }
    function searchOffset(group) {
        let offset = 0;
        for (let i = 0; i < group; i++)
            offset += runner.modelForRow(i) ? runner.modelForRow(i).count : 0;
        return offset;
    }
    function searchCount() { return searchOffset(runner.count); }
    function move(step) {
        const count = view === "search" ? searchCount() : view === "programs" ? (programsModel || programs).count : favorites.count;
        if (count === 0)
            return;
        current = current < 0 ? (step > 0 ? 0 : count - 1) : (current + step + count) % count;
        if (view === "programs")
            programList.positionViewAtIndex(current, ListView.Contain);
    }
    function activateCurrent() {
        if (view === "search") {
            for (let i = 0, offset = 0; i < runner.count; i++) {
                const matches = runner.modelForRow(i);
                if (matches && current >= offset && current < offset + matches.count)
                    return launch(matches, current - offset);
                offset += matches ? matches.count : 0;
            }
        } else if (view === "programs" && current >= 0) {
            activateProgram(current);
        } else if (current >= 0) {
            launch(favorites, current);
        }
    }
}
