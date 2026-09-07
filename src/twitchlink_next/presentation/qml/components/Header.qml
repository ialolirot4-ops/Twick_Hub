import QtQuick
import QtQuick.Layouts
import TwitchLinkNext 1.0

Rectangle {
    id: root
    height: 56
    color: Theme.background

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.border
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingLg
        anchors.rightMargin: Theme.spacingLg
        spacing: Theme.spacingMd

        Text {
            text: {
                for (var i = 0; i < NavigationController.pages.length; i++) {
                    if (NavigationController.pages[i].id === NavigationController.currentPageId)
                        return NavigationController.pages[i].label;
                }
                return "";
            }
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeHeading
            font.bold: true
        }

        Item { Layout.fillWidth: true }

        // Dark/light toggle — a plain hit target rather than a switch
        // graphic, to keep this shell phase's chrome minimal.
        Rectangle {
            width: 72
            height: 32
            radius: height / 2
            color: Theme.surface
            border.width: 1
            border.color: Theme.border

            Text {
                anchors.centerIn: parent
                text: Theme.darkMode ? "Dark" : "Light"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeCaption
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: Theme.toggle()
            }
        }
    }
}
