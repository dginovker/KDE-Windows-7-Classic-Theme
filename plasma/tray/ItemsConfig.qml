pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import QtQuick.Window
import org.kde.kquickcontrols as KQuickControls
import org.kde.plasma.plasmoid

Controls.ScrollView {
    id: page
    property bool cfg_showAllItems
    property bool cfg_pin
    property var cfg_extraItems: []
    property var cfg_shownItems: []
    property var cfg_hiddenItems: []
    property var cfg_disabledStatusNotifiers: []
    readonly property var backend: Plasmoid
    readonly property var itemsWindow: Window.window
    onItemsWindowChanged: if (itemsWindow) backend?.trackItemsWindow(itemsWindow)
    property var pendingShortcuts: new Map()
    readonly property bool unsavedChanges: pendingShortcuts.size > 0
    readonly property var options: [qsTr("Show when relevant"), qsTr("Always show"), qsTr("Only in popup"), qsTr("Disabled")]
    readonly property var notifiers: {
        const entries = new Map();
        for (const n of backend?.statusNotifiers?.items ?? []) {
            entries.set(n.persistentId, {id: n.persistentId, name: n.Title || n.Id, notifier: true});
        }
        for (const app of backend?.backgroundApps?.items ?? []) {
            if (!entries.has(app.id)) entries.set(app.id, {id: app.id, name: app.name, notifier: true});
        }
        return [...entries.values()];
    }

    function stageShortcut(applet, shortcut) {
        const next = new Map(pendingShortcuts);
        if (shortcut === applet.globalShortcut.toString()) {
            next.delete(applet);
        } else {
            next.set(applet, shortcut);
        }
        pendingShortcuts = next;
    }

    function saveConfig() {
        // The applet can disappear while the dialog is open (for example, after a service exits).
        for (const applet of backend.applets) {
            if (pendingShortcuts.has(applet)) {
                applet.globalShortcut = pendingShortcuts.get(applet);
            }
        }
        pendingShortcuts = new Map();
    }

    function put(list, id, include) {
        const result = Array.from(list).filter(candidate => candidate !== id);
        if (include) result.push(id);
        return result;
    }

    function policy(entry) {
        if (entry.notifier ? cfg_disabledStatusNotifiers.includes(entry.id) : !cfg_extraItems.includes(entry.id)) return 3;
        if (cfg_shownItems.includes(entry.id)) return 1;
        if (cfg_hiddenItems.includes(entry.id)) return 2;
        return 0;
    }

    // Repeater re-parents delegates into the layout; Qt can regenerate them while that layout is destroyed.
    ListView {
        clip: true
        spacing: 5
        header: ColumnLayout {
            width: page.availableWidth
            Controls.CheckBox {
                text: qsTr("Show all items in the notification area")
                checked: page.cfg_showAllItems
                onToggled: page.cfg_showAllItems = checked
            }
            Controls.CheckBox {
                text: qsTr("Keep the hidden-icons popup open")
                checked: page.cfg_pin
                onToggled: page.cfg_pin = checked
            }
        }
        model: page.backend?.appletChoices.concat(page.notifiers) ?? []
        delegate: RowLayout {
            id: row
            width: page.availableWidth
            required property var modelData
            readonly property var applet: modelData.notifier ? null
                : page.backend?.applets.find(candidate => page.backend.settingsId(candidate) === modelData.id) ?? null
            Controls.Label {
                Layout.fillWidth: true
                text: row.modelData.name
                elide: Text.ElideRight
            }
            Controls.ComboBox {
                id: visibility
                Accessible.name: row.modelData.name
                model: row.modelData.mandatory ? [...page.options.slice(0, 3), qsTr("Hide icon")] : page.options
                currentIndex: page.policy(row.modelData)
                onActivated: value => {
                    const {id, notifier} = row.modelData;
                    page.cfg_shownItems = page.put(page.cfg_shownItems, id, value === 1);
                    page.cfg_hiddenItems = page.put(page.cfg_hiddenItems, id, value === 2);
                    if (notifier) {
                        page.cfg_disabledStatusNotifiers = page.put(page.cfg_disabledStatusNotifiers, id, value === 3);
                    } else {
                        page.cfg_extraItems = page.put(page.cfg_extraItems, id, value !== 3);
                    }
                }
            }
            KQuickControls.KeySequenceItem {
                visible: !row.modelData.notifier
                enabled: row.applet !== null && visibility.currentIndex !== 3
                keySequence: page.pendingShortcuts.get(row.applet) ?? row.applet?.globalShortcut ?? ""
                onKeySequenceModified: if (row.applet) page.stageShortcut(row.applet, keySequence.toString())
            }
            Controls.Button {
                readonly property var configureAction: row.applet?.internalAction("configure") ?? null
                visible: configureAction?.visible ?? false
                enabled: configureAction?.enabled ?? false
                Accessible.name: configureAction?.text ?? ""
                icon.name: "configure"
                onClicked: configureAction.trigger()
            }
        }
    }
}
