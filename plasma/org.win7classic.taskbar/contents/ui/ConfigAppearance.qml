import QtQuick.Controls as QQC2
import QtQuick.Layouts

ColumnLayout {
    property alias cfg_plainExplorerPin: plainExplorerPin.checked

    QQC2.CheckBox {
        id: plainExplorerPin
        text: i18n("Use a plain folder icon for the closed Explorer pin")
    }
}
