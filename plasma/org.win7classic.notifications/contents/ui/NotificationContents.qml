// SPDX-License-Identifier: GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.notificationmanager as NM
import org.kde.taskmanager as TaskManager

ColumnLayout {
    id: root
    required property var entry
    required property int row
    required property NM.Notifications source
    property TaskManager.TasksModel tasks
    readonly property var matchingWindow: {
        if (!tasks || entry.hasDefaultAction || !entry.desktopEntry)
            return null;
        let best = null;
        let stack = -1;
        for (let row = 0; row < tasks.count; ++row) {
            const idx = tasks.index(row, 0);
            if (tasks.data(idx, TaskManager.AbstractTasksModel.AppId) === entry.desktopEntry + ".desktop") {
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
    property bool showSettings: false
    readonly property alias editing: replyField.activeFocus
    readonly property bool pendingReply: replyField.length > 0
    readonly property bool job: entry.type === NM.Notifications.JobType
    readonly property bool hasActions: entry.hasDefaultAction || entry.hasReplyAction || entry.actionNames.length > 0 || entry.configureActionLabel.length > 0
    readonly property int actionBehavior: entry.resident ? NM.Notifications.None : NM.Notifications.Close

    signal wantsFocus()

    function index() { return source.index(row, 0); }

    function activateDefaultAction() {
        if (entry.hasDefaultAction)
            source.invokeDefaultAction(index(), actionBehavior);
        else if (matchingWindow?.valid) {
            tasks.requestActivate(matchingWindow);
            if (!entry.resident)
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
        enabled: root.entry.configurable
        onTapped: settingsMenu.popup()
    }
    QQC.Menu {
        id: settingsMenu
        QQC.MenuItem {
            text: qsTr("Configure Notifications…")
            onTriggered: root.source.configure(root.index())
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Kirigami.Icon {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            source: root.entry.image || root.entry.iconName || root.entry.applicationIconName
            visible: source !== undefined && source !== ""
        }
        Text {
            Layout.fillWidth: true
            textFormat: Text.PlainText
            text: root.entry.summary || root.entry.applicationName
            font.bold: true
            color: "black"
            wrapMode: Text.Wrap
            renderType: Text.NativeRendering
            TapHandler { enabled: root.entry.hasDefaultAction || root.matchingWindow?.valid === true; onTapped: root.activateDefaultAction() }
        }
        QQC.ToolButton {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            visible: root.entry.closable || root.entry.dismissable
            text: "×"
            Accessible.name: root.entry.closable ? qsTr("Close notification") : qsTr("Dismiss notification")
            onClicked: {
                if (root.entry.closable)
                    root.source.close(root.index());
                else
                    root.entry.dismissed = true;
            }
        }
    }

    Text {
        Layout.fillWidth: true
        visible: text.length > 0
        text: root.entry.body
        // The canonical model supplies the server-sanitized notification body.
        textFormat: Text.StyledText
        wrapMode: Text.Wrap
        color: "black"
        renderType: Text.NativeRendering
        onLinkActivated: link => Qt.openUrlExternally(link)
        TapHandler {
            enabled: root.entry.hasDefaultAction || root.matchingWindow?.valid === true
            onTapped: if (!parent.linkAt(point.position.x, point.position.y)) root.activateDefaultAction()
        }
    }

    QQC.ProgressBar {
        Layout.fillWidth: true
        visible: root.job
        from: 0; to: 100
        value: root.entry.percentage
    }

    Flow {
        Layout.fillWidth: true
        spacing: 3
        Repeater {
            model: root.entry.actionLabels
            QQC.Button {
                required property int index
                required property string modelData
                text: modelData
                onClicked: root.source.invokeAction(root.index(), root.entry.actionNames[index], root.actionBehavior)
            }
        }
        Repeater {
            model: root.entry.urls
            QQC.Button {
                required property url modelData
                text: qsTr("Open attachment")
                onClicked: {
                    Qt.openUrlExternally(modelData);
                    if (root.entry.resident)
                        root.entry.expired = true;
                    else
                        root.source.close(root.index());
                }
            }
        }
        QQC.Button {
            visible: root.entry.hasReplyAction && !root.replying
            text: root.entry.replyActionLabel || qsTr("Reply")
            onClicked: {
                root.replying = true;
                root.wantsFocus();
                replyField.forceActiveFocus();
            }
        }
        QQC.Button {
            visible: root.entry.configurable && (root.showSettings || root.entry.configureActionLabel.length > 0)
            text: root.entry.configureActionLabel || qsTr("Settings")
            onClicked: root.source.configure(root.index())
        }
        QQC.Button {
            visible: root.job && root.entry.suspendable && root.entry.jobState !== NM.Notifications.JobStateStopped
            text: root.entry.jobState === NM.Notifications.JobStateSuspended ? qsTr("Resume") : qsTr("Pause")
            onClicked: {
                if (root.entry.jobState === NM.Notifications.JobStateSuspended)
                    root.source.resumeJob(root.index());
                else
                    root.source.suspendJob(root.index());
            }
        }
        QQC.Button {
            visible: root.job && root.entry.killable && root.entry.jobState !== NM.Notifications.JobStateStopped
            text: qsTr("Cancel")
            onClicked: root.source.killJob(root.index())
        }
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.replying
        QQC.TextField {
            id: replyField
            Layout.fillWidth: true
            placeholderText: root.entry.replyPlaceholderText || qsTr("Reply")
            onAccepted: root.submitReply()
        }
        QQC.Button {
            text: root.entry.replySubmitButtonText || qsTr("Send")
            icon.name: root.entry.replySubmitButtonIconName
            enabled: replyField.text.trim().length > 0
            onClicked: root.submitReply()
        }
    }
}
