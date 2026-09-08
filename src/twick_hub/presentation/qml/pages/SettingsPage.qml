import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

ScrollView {
    id: root
    contentWidth: availableWidth

    // Mock only: real values arrive with FASE 13, backed by the settings
    // table in docs/architecture-decisions.md's persistence section.
    property var sections: [
        {
            title: "General", rows: [
                { label: "Language", value: "English" },
                { label: "Time zone", value: "System default" }
            ]
        },
        {
            title: "Downloads", rows: [
                { label: "Save location", value: "~/Videos/TwickHub" },
                { label: "Filename template", value: "{channel}/{title} ({date})" },
                { label: "Max concurrent downloads", value: "3" }
            ]
        },
        {
            title: "Twitch", rows: [
                { label: "Realtime notifications", value: "EventSub (WebSocket)" }
            ]
        },
        {
            title: "Kick", rows: [
                { label: "Live status checks", value: "Adaptive polling" }
            ]
        }
    ]

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingLg

        Repeater {
            model: root.sections
            delegate: ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: Theme.spacingLg
                Layout.bottomMargin: 0
                spacing: Theme.spacingSm

                Text { text: modelData.title; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeSubheading; font.bold: true }

                SectionCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: rowsColumn.implicitHeight + Theme.spacingMd * 2

                    ColumnLayout {
                        id: rowsColumn
                        anchors.fill: parent
                        spacing: Theme.spacingSm

                        Repeater {
                            model: modelData.rows
                            delegate: RowLayout {
                                Layout.fillWidth: true
                                Text { text: modelData.label; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeBody; Layout.fillWidth: true }
                                Text { text: modelData.value; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeBody }
                            }
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.spacingLg
            Layout.bottomMargin: 0
            spacing: Theme.spacingSm

            Text { text: "Appearance"; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeSubheading; font.bold: true }

            SectionCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                RowLayout {
                    anchors.fill: parent
                    Text { text: "Theme"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeBody; Layout.fillWidth: true }
                    AppButton { text: Theme.darkMode ? "Dark" : "Light"; onClicked: Theme.toggle() }
                }
            }
        }

        RowLayout {
            Layout.margins: Theme.spacingLg
            Layout.topMargin: 0
            AppButton {
                text: "Reset to defaults"
                onClicked: resetDialog.open()
            }
        }

        Item { Layout.preferredHeight: Theme.spacingLg }
    }

    AppDialog {
        id: resetDialog
        title: "Reset all settings?"
        message: "General, Downloads, Twitch, and Kick settings all go back to their defaults. This doesn't affect your downloaded files or history."
        confirmLabel: "Reset"
        cancelLabel: "Keep my settings"
        destructive: true
        onAccepted: ToastController.success("Settings reset to defaults")
    }
}
