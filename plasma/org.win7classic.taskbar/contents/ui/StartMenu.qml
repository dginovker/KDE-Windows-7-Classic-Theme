import QtCore
import QtQuick
import "../../../../../win7-classic/primitives2" as Classic
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

    readonly property color face: Classic.Palette.face
    readonly property color highlight: Classic.Palette.selection
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


        Classic.Raster { anchors.fill: parent; fill: menu.face; edge: Classic.Raster.Raised }

        component Etch: Classic.Raster { height: 2; separator: true }
        component Label: Text {
            font: menu.uiFont
            color: "black"
            renderType: Text.NativeRendering
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        component Triangle: Classic.Raster {
            property bool pointsLeft: false
            property color color: "black"
            width: 4; height: 7
            glyph: pointsLeft ? Classic.Raster.ArrowLeft : Classic.Raster.ArrowRight
            glyphColor: color
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
            Classic.Raster { x: 253; y: 3; width: 2; height: 421; edge: Classic.Raster.SunkenOuter; flags: Classic.Raster.Left | Classic.Raster.Right }

            Item {
                x: 300; y: 8; width: 62; height: 62
                Kirigami.Icon { x: 7; y: 7; width: 48; height: 46; source: user.faceIconUrl.toString() ? user.faceIconUrl : "user-identity" }
                Image { anchors.fill: parent; source: "assets/account-frame.png"; smooth: false }
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
        Classic.Raster { x: 3; y: 424; width: 399; height: 2; edge: Classic.Raster.SunkenOuter; flags: Classic.Raster.Top | Classic.Raster.Bottom }

        Item {
            id: searchBox
            // Windows widens the box by 3px while searching, when the magnifier turns into a clear button.
            x: 7; y: 428; width: menu.view === "search" ? 224 : 221; height: 23
            Classic.Raster { anchors.fill: parent; fill: "white"; edge: Classic.Raster.Sunken }
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
        Image {
            x: searchBox.x + searchBox.width; y: 428; width: 22; height: 23
            source: search.text.length ? "assets/clear.png" : "assets/search.png"
            smooth: false
            MouseArea { anchors.fill: parent; onClicked: search.text = "" }
        }

        // Shut down: one raised button with a separate arrow part, like Windows' split button.
        Item {
            id: shutdown
            x: 257; y: 428; width: 86; height: 23
            readonly property bool mainPressed: shutdownMain.pressed && shutdownMain.containsMouse
            readonly property bool arrowPressed: shutdownArrow.pressed && shutdownArrow.containsMouse
            Classic.Raster { anchors.fill: parent; button: true }
            Classic.Raster { x: 0; width: 73; height: 23; button: true; pressed: true; visible: shutdown.mainPressed }
            Classic.Raster { x: 72; width: 14; height: 23; button: true; pressed: true; visible: shutdown.arrowPressed }
            Classic.Raster { x: 71; y: 1; width: 1; height: 20; edge: Classic.Raster.SunkenOuter; flags: Classic.Raster.Left; visible: !shutdown.mainPressed && !shutdown.arrowPressed }
            Classic.Raster { x: 72; width: 1; height: 22; edge: Classic.Raster.SunkenOuter; flags: Classic.Raster.Right; visible: !shutdown.mainPressed && !shutdown.arrowPressed }
            Label { x: 1 + (shutdown.mainPressed ? 1 : 0); y: shutdown.mainPressed ? 1 : 0; width: 70; height: 22; horizontalAlignment: Text.AlignHCenter; text: "Shut down" }
            Triangle { x: 77 + (shutdown.arrowPressed ? 1 : 0); y: 7 + (shutdown.arrowPressed ? 1 : 0) }
            Classic.Raster { x: 4; y: 4; width: 64; height: 15; focused: shutdownMain.activeFocus }
            MouseArea {
                id: shutdownMain
                x: 0; width: 71; height: 23
                hoverEnabled: true
                activeFocusOnTab: true
                // Confirmation protects unsaved work from a misplaced click or key.
                function confirm() { menu.close(); menu.runCommand("org.kde.LogoutPrompt", "/LogoutPrompt", "org.kde.LogoutPrompt", "promptShutDown", [], "()"); }
                onClicked: confirm()
                Keys.onReturnPressed: confirm()
                Keys.onSpacePressed: confirm()
            }
            MouseArea {
                id: shutdownArrow
                x: 72; width: 14; height: 23
                hoverEnabled: true
                activeFocusOnTab: true
                function confirm() { menu.close(); menu.runCommand("org.kde.LogoutPrompt", "/LogoutPrompt", "org.kde.LogoutPrompt", "promptAll", [], "()"); }
                onClicked: confirm()
                Keys.onReturnPressed: confirm()
                Keys.onSpacePressed: confirm()
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
