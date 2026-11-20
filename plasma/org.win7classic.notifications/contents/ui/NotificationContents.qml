// SPDX-License-Identifier: GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore
import org.kde.notificationmanager as NM
import org.kde.taskmanager as TaskManager

ColumnLayout {
    id: root
    required property var entry
    required property int row
    required property NM.Notifications source
    property TaskManager.TasksModel tasks
    readonly property var matchingWindow: {
        if (!tasks || entry?.hasDefaultAction || !entry?.desktopEntry)
            return null;
        let best = null;
        let stack = -1;
        for (let row = 0; row < tasks.rowCount(); ++row) {
            const idx = tasks.index(row, 0);
            if (tasks.data(idx, TaskManager.AbstractTasksModel.AppId) === entry?.desktopEntry + ".desktop") {
                const order = tasks.data(idx, TaskManager.AbstractTasksModel.StackingOrder);
                if (order > stack) {
                    best = tasks.makePersistentModelIndex(row);
                    stack = order;
                }
            }
        }
        return best;
    }
    property bool replying: false
    readonly property alias editing: replyField.activeFocus
    readonly property bool pendingReply: replyField.length > 0
    visible: entry !== null
    readonly property bool hasActions: !!entry?.hasDefaultAction || !!entry?.hasReplyAction || (entry?.actionNames.length ?? 0) > 0 || (entry?.configureActionLabel.length ?? 0) > 0
    readonly property string sourceLabel: [entry?.applicationName, entry?.originName].filter(Boolean).join("\n")
    readonly property string configureLabel: entry?.configureActionLabel || qsTr("Configure Notifications…")
    readonly property int actionBehavior: entry?.resident ? NM.Notifications.None : NM.Notifications.Close

    function index() { return source.index(row, 0); }

    function activateDefaultAction() {
        if (entry?.hasDefaultAction)
            source.invokeDefaultAction(index(), actionBehavior);
        else if (matchingWindow?.valid) {
            tasks.requestActivate(matchingWindow);
            if (!entry?.resident)
                source.close(index());
        }
    }

    function submitReply() {
        if (replyField.text.trim().length > 0) {
            const text = replyField.text;
            replyField.clear();
            replying = false;
            source.reply(index(), text, actionBehavior);
        }
    }

    spacing: 2

    TapHandler {
        acceptedButtons: Qt.RightButton
        enabled: !!root.entry?.configurable
        onTapped: settingsMenu.popup()
    }
    QQC.Menu {
        id: settingsMenu
        QQC.MenuItem {
            text: root.configureLabel
            onTriggered: root.source.configure(root.index())
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Kirigami.Icon {
            Layout.alignment: Qt.AlignTop
            Layout.leftMargin: 6
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            readonly property string iconName: root.entry?.iconName ?? ""
            source: root.entry?.image || (iconName === "dialog-information" || !iconName
                ? Qt.resolvedUrl("balloon-information.png") : iconName)
            visible: source !== undefined && source !== ""
        }
        Text {
            Layout.fillWidth: true
            textFormat: Text.PlainText
            text: root.entry ? (root.entry.summary || root.entry.applicationName) : ""
            font.bold: true
            color: "black"
            wrapMode: Text.Wrap
            renderType: Text.NativeRendering
            Accessible.description: root.sourceLabel
            PlasmaCore.ToolTipArea {
                anchors.fill: parent
                mainText: root.entry?.applicationName ?? ""
                subText: root.entry?.originName ?? ""
                textFormat: Text.PlainText
            }
            TapHandler { enabled: root.entry?.hasDefaultAction || root.matchingWindow?.valid === true; onTapped: root.activateDefaultAction() }
        }
        QQC.ToolButton {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 12
            Layout.preferredHeight: 15
            visible: !!root.entry?.configurable
            Accessible.name: root.configureLabel
            PlasmaCore.ToolTipArea {
                anchors.fill: parent
                mainText: root.configureLabel
                textFormat: Text.PlainText
            }
            background: Image { source: "balloon-configure.png" }
            onClicked: root.source.configure(root.index())
        }
        QQC.ToolButton {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 12
            Layout.preferredHeight: 15
            visible: !!root.entry?.closable || !!root.entry?.dismissable
            background: Image { source: "balloon-close.png" }
            Accessible.name: root.entry?.closable ? qsTr("Close notification") : qsTr("Dismiss notification")
            onClicked: {
                if (root.entry?.closable)
                    root.source.close(root.index());
                else
                    root.entry.dismissed = true;
            }
        }
    }

    Text {
        Layout.fillWidth: true
        Layout.leftMargin: 28
        visible: text.length > 0
        text: root.entry?.body ?? ""
        // The canonical model supplies the server-sanitized notification body.
        textFormat: Text.StyledText
        wrapMode: Text.Wrap
        color: "black"
        renderType: Text.NativeRendering
        onLinkActivated: link => Qt.openUrlExternally(link)
        TapHandler {
            enabled: root.entry?.hasDefaultAction || root.matchingWindow?.valid === true
            onTapped: if (!parent.linkAt(point.position.x, point.position.y)) root.activateDefaultAction()
        }
    }

    Flow {
        Layout.fillWidth: true
        spacing: 3
        Repeater {
            model: root.entry?.actionLabels
            QQC.Button {
                required property int index
                required property string modelData
                text: modelData
                onClicked: root.source.invokeAction(root.index(), root.entry?.actionNames[index], root.actionBehavior)
            }
        }
        QQC.Button {
            visible: !!root.entry?.hasReplyAction && !root.replying
            text: root.entry?.replyActionLabel || qsTr("Reply")
            onClicked: {
                root.replying = true;
                replyField.forceActiveFocus();
            }
        }

    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.replying
        QQC.TextField {
            id: replyField
            Layout.fillWidth: true
            placeholderText: root.entry?.replyPlaceholderText || qsTr("Reply")
            onAccepted: root.submitReply()
        }
        QQC.Button {
            text: root.entry?.replySubmitButtonText || qsTr("Send")
            icon.name: root.entry?.replySubmitButtonIconName ?? ""
            enabled: replyField.text.trim().length > 0
            onClicked: root.submitReply()
        }
    }
}
