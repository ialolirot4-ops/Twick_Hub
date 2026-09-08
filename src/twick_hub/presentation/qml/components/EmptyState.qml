import QtQuick
import QtQuick.Layouts
import TwickHub 1.0

// An empty screen is an invitation to act, not an apology — callers
// supply a concrete next step via actionLabel/actionRequested rather than
// a generic "nothing here yet."
//
// Root is a plain Item (not the inner ColumnLayout) so this component
// works both anchored directly (anchors.fill: parent inside a plain Item)
// and inside a Layout (Layout.fillWidth/fillHeight) without Qt's
// "anchors on a layout-managed item" warning — the centering anchor below
// is on the inner column, relative to this root, never on the root itself.
Item {
    id: root
    property string title: ""
    property string description: ""
    property string actionLabel: ""
    signal actionRequested()

    ColumnLayout {
        anchors.centerIn: parent
        spacing: Theme.spacingSm
        width: 320

        Text {
            Layout.fillWidth: true
            Layout.bottomMargin: Theme.spacingXs
            text: root.title
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeSubheading
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            text: root.description
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeBody
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        AppButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Theme.spacingMd
            visible: root.actionLabel.length > 0
            text: root.actionLabel
            primary: true
            onClicked: root.actionRequested()
        }
    }
}
