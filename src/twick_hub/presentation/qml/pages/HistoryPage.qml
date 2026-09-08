import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

ScrollView {
    id: root
    contentWidth: availableWidth

    property var mockHistory: [
        { name: "northernlion — VOD part 11", platform: "twitch", date: "Sep 3, 2026", size: "2.1 GB" },
        { name: "adin — clip", platform: "kick", date: "Sep 2, 2026", size: "84 MB" },
        { name: "hasanabi — full stream", platform: "twitch", date: "Aug 30, 2026", size: "4.6 GB" }
    ]

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingSm

        Repeater {
            model: root.mockHistory
            delegate: SectionCard {
                Layout.fillWidth: true
                Layout.margins: Theme.spacingLg
                Layout.bottomMargin: 0
                Layout.preferredHeight: 56
                RowLayout {
                    anchors.fill: parent
                    spacing: Theme.spacingSm
                    PlatformBadge { platform: modelData.platform }
                    Text {
                        text: modelData.name
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSizeBody
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Text { text: modelData.size; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeCaption }
                    Text { text: modelData.date; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeCaption }
                    AppButton { text: "Open folder" }
                }
            }
        }

        Item { Layout.preferredHeight: Theme.spacingLg }
    }
}
