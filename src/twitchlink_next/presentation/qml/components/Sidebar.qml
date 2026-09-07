import QtQuick
import QtQuick.Layouts
import TwitchLinkNext 1.0

Rectangle {
    id: root
    width: 220
    color: Theme.surface
    border.width: 0

    Rectangle {
        // hairline separator instead of a shadow — cheaper to render and
        // reads cleaner at low DPI.
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.border
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingXs

        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: Theme.spacingMd
            spacing: Theme.spacingSm

            Rectangle {
                width: 28
                height: 28
                radius: Theme.radiusSm
                color: Theme.accent
                Text {
                    anchors.centerIn: parent
                    text: "TL"
                    color: Theme.accentText
                    font.bold: true
                    font.pixelSize: Theme.fontSizeCaption
                }
            }
            Text {
                text: "TwitchLink Next"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeSubheading
                font.bold: true
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }

        Repeater {
            model: NavigationController.pages
            delegate: SidebarItem {
                Layout.fillWidth: true
                pageId: modelData.id
                label: modelData.label
            }
        }

        Item { Layout.fillHeight: true } // pushes nothing below for now; FASE 13 may add a footer shortcut here
    }
}
