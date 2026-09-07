import QtQuick
import QtQuick.Layouts
import TwitchLinkNext 1.0

// States its cause and the fix in the interface's own voice — never
// "Oops, something went wrong." Same root-Item-plus-centered-inner-column
// structure as EmptyState.qml, and for the same reason — see its comment.
Item {
    id: root
    property string title: "Couldn't load this"
    property string description: ""
    property string actionLabel: "Retry"
    signal actionRequested()

    ColumnLayout {
        anchors.centerIn: parent
        spacing: Theme.spacingSm
        width: 320

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: Theme.spacingXs
            width: 40
            height: 40
            radius: 20
            color: Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.16)
            Text {
                anchors.centerIn: parent
                text: "!"
                color: Theme.danger
                font.pixelSize: Theme.fontSizeSubheading
                font.bold: true
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeSubheading
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            visible: root.description.length > 0
            text: root.description
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeBody
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        AppButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Theme.spacingMd
            text: root.actionLabel
            onClicked: root.actionRequested()
        }
    }
}
