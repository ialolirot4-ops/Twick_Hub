import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0

Dialog {
    id: root
    property string message: ""
    property string confirmLabel: "Confirm"
    property string cancelLabel: "Cancel"
    property bool destructive: false

    modal: true
    anchors.centerIn: parent
    width: 360
    padding: Theme.spacingLg

    background: Rectangle {
        color: Theme.surfaceElevated
        radius: Theme.radiusMd
        border.width: 1
        border.color: Theme.border
    }

    header: Text {
        text: root.title
        color: Theme.textPrimary
        font.pixelSize: Theme.fontSizeSubheading
        font.bold: true
        padding: Theme.spacingLg
        bottomPadding: 0
    }

    contentItem: Text {
        text: root.message
        color: Theme.textSecondary
        font.pixelSize: Theme.fontSizeBody
        wrapMode: Text.WordWrap
    }

    footer: Item {
        implicitHeight: footerRow.implicitHeight + Theme.spacingLg * 2
        RowLayout {
            id: footerRow
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingSm
            layoutDirection: Qt.RightToLeft

            AppButton {
                text: root.confirmLabel
                primary: !root.destructive
                onClicked: root.accept()
            }
            AppButton {
                text: root.cancelLabel
                onClicked: root.reject()
            }
        }
    }
}
