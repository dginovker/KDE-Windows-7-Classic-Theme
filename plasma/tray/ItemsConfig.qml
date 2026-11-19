pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.plasma.plasmoid

Controls.ScrollView {
    id: page
    property alias cfg_showAllItems: showAll.checked
    property alias cfg_pin: pin.checked
    property var cfg_extraItems: []
    property var cfg_shownItems: []
    property var cfg_hiddenItems: []
    property var cfg_disabledStatusNotifiers: []
    readonly property var backend: Plasmoid
    readonly property var options: [qsTr("Show when relevant"), qsTr("Always show"), qsTr("Only in popup"), qsTr("Disabled")]
    readonly property var notifiers: {
        const entries = new Map();
        for (const n of backend.statusNotifiers?.items ?? []) {
            entries.set(n.persistentId, {id: n.persistentId, name: n.Title || n.Id, notifier: true});
        }
        return [...entries.values()];
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

    ColumnLayout {
        width: page.availableWidth
        Controls.CheckBox { id: showAll; text: qsTr("Show all items in the notification area") }
        Controls.CheckBox { id: pin; text: qsTr("Keep the hidden-icons popup open") }
        Repeater {
            model: page.backend.appletChoices.concat(page.notifiers)
            delegate: RowLayout {
                id: row
                required property var modelData
                Controls.Label {
                    Layout.fillWidth: true
                    text: row.modelData.name
                    elide: Text.ElideRight
                }
                Controls.ComboBox {
                    Accessible.name: row.modelData.name
                    model: page.options
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
            }
        }
    }
}
