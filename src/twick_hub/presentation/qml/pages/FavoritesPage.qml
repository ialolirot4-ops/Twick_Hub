import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

ScrollView {
    id: root
    contentWidth: availableWidth

    property var mockFavorites: [
        { name: "northernlion", platform: "twitch", live: true },
        { name: "hasanabi", platform: "twitch", live: false },
        { name: "xqc", platform: "kick", live: true },
        { name: "adin", platform: "kick", live: false },
        { name: "pokimane", platform: "twitch", live: false }
    ]

    GridLayout {
        width: root.availableWidth
        columns: Math.max(1, Math.floor(width / 220))
        columnSpacing: Theme.spacingMd
        rowSpacing: Theme.spacingMd
        Layout.margins: Theme.spacingLg

        Repeater {
            model: root.mockFavorites
            delegate: SectionCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 92

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.spacingXs

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: modelData.name
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontSizeBody
                            font.bold: true
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            visible: modelData.live
                            width: 8; height: 8; radius: 4
                            color: Theme.success
                        }
                    }

                    PlatformBadge { platform: modelData.platform }

                    Text {
                        text: modelData.live ? "Live now" : "Offline"
                        color: modelData.live ? Theme.success : Theme.textSecondary
                        font.pixelSize: Theme.fontSizeCaption
                    }
                }
            }
        }
    }
}
