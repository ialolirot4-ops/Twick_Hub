import QtQuick
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

ColumnLayout {
    id: root
    anchors.fill: parent
    anchors.margins: Theme.spacingLg
    spacing: Theme.spacingMd

    RowLayout {
        spacing: Theme.spacingMd
        Rectangle {
            width: 48; height: 48
            radius: Theme.radiusMd
            color: Theme.accent
            Text { anchors.centerIn: parent; text: "TH"; color: Theme.accentText; font.bold: true; font.pixelSize: Theme.fontSizeSubheading }
        }
        ColumnLayout {
            spacing: 0
            Text { text: "Twick Hub"; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeHeading; font.bold: true }
            Text { text: "Version 0.1.0"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeCaption }
        }
    }

    SectionCard {
        Layout.fillWidth: true
        Layout.preferredHeight: aboutColumn.implicitHeight + Theme.spacingMd * 2

        ColumnLayout {
            id: aboutColumn
            anchors.fill: parent
            spacing: Theme.spacingSm

            Text {
                text: "A ground-up rewrite of TwitchLink adding Kick as a first-class platform alongside Twitch, built on PySide6, QML, and SQLAlchemy."
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeBody
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            RowLayout {
                spacing: Theme.spacingSm
                Text { text: "Supported platforms:"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeCaption }
                PlatformBadge { platform: "twitch" }
                PlatformBadge { platform: "kick" }
            }
        }
    }

    Item { Layout.fillHeight: true }
}
