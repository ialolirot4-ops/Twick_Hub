import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

Item {
    id: root
    property int filterIndex: 0 // 0 all, 1 twitch, 2 kick
    property var mockResults: [
        { title: "northernlion", platform: "twitch", kind: "Channel" },
        { title: "Full playthrough VOD — Part 12", platform: "twitch", kind: "Video" },
        { title: "xqc", platform: "kick", kind: "Channel" },
        { title: "Clutch moment clip", platform: "kick", kind: "Clip" }
    ]

    readonly property var filteredResults: {
        if (root.filterIndex === 1) return root.mockResults.filter(r => r.platform === "twitch");
        if (root.filterIndex === 2) return root.mockResults.filter(r => r.platform === "kick");
        return root.mockResults;
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingMd

        TextField {
            id: searchField
            Layout.fillWidth: true
            placeholderText: "Search a channel, VOD, or clip URL — Twitch or Kick"
            color: Theme.textPrimary
            placeholderTextColor: Theme.textSecondary
            font.pixelSize: Theme.fontSizeBody
            background: Rectangle {
                color: Theme.surface
                radius: Theme.radiusSm
                border.width: 1
                border.color: searchField.activeFocus ? Theme.accent : Theme.border
            }
            leftPadding: Theme.spacingMd
            rightPadding: Theme.spacingMd
            topPadding: Theme.spacingSm
            bottomPadding: Theme.spacingSm
        }

        RowLayout {
            spacing: Theme.spacingSm

            Repeater {
                model: ["All", "Twitch", "Kick"]
                delegate: AppButton {
                    text: modelData
                    primary: root.filterIndex === index
                    onClicked: root.filterIndex = index
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredResults.length > 0
            spacing: Theme.spacingSm

            Repeater {
                model: root.filteredResults
                delegate: SectionCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 56
                    RowLayout {
                        anchors.fill: parent
                        spacing: Theme.spacingSm
                        PlatformBadge { platform: modelData.platform }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text { text: modelData.title; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeBody; elide: Text.ElideRight }
                            Text { text: modelData.kind; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeCaption }
                        }
                        AppButton { text: "Download" }
                    }
                }
            }
        }

        EmptyState {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredResults.length === 0
            title: "No results for this filter"
            description: "Try a different platform tab, or paste a direct channel/VOD/clip URL."
        }
    }
}
