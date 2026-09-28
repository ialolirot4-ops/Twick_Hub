import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

ScrollView {
    id: root
    contentWidth: availableWidth

    property bool refreshing: false

    // RISK-UI-04 fix: Favorites/Downloads counters below are real (reuse the
    // same favoritesModel/downloadsModel bridges FASE 21b already wired for
    // their own pages — no new bridge, no network). "Live now" and "Recent
    // activity" stay mock: they need Twitch/Kick adapters (21c) or a real
    // notifications/history-derived feed, neither in scope here.
    Component.onCompleted: {
        favoritesModel.refresh();
        downloadsModel.refresh();
    }

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingLg

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.spacingLg
            Layout.bottomMargin: 0

            Text {
                text: "Welcome back"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeHeading
                font.bold: true
                Layout.fillWidth: true
            }

            AppButton {
                text: root.refreshing ? "Refreshing…" : "Refresh"
                enabled: !root.refreshing
                onClicked: {
                    root.refreshing = true;
                    refreshTimer.start();
                }
            }
        }

        Timer {
            id: refreshTimer
            interval: 900
            onTriggered: {
                root.refreshing = false;
                ToastController.success("Everything is up to date");
            }
        }

        Loader {
            Layout.leftMargin: Theme.spacingLg
            active: root.refreshing
            sourceComponent: LoadingIndicator { label: "Checking favorites…" }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.spacingLg
            Layout.rightMargin: Theme.spacingLg
            columns: 3
            columnSpacing: Theme.spacingMd
            rowSpacing: Theme.spacingMd

            Repeater {
                model: [
                    // Still mock — needs 21c/21d (no live adapters yet).
                    { label: "Live now", value: "2" },
                    { label: "Downloads in progress", value: String(downloadsModel.count) },
                    { label: "Favorites", value: String(favoritesModel.count) }
                ]
                delegate: SectionCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 84
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.spacingXs
                        Text { text: modelData.value; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeHeading; font.bold: true }
                        Text { text: modelData.label; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeCaption }
                    }
                }
            }
        }

        SectionCard {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.spacingLg
            Layout.rightMargin: Theme.spacingLg
            Layout.bottomMargin: Theme.spacingLg
            Layout.preferredHeight: activityColumn.implicitHeight + Theme.spacingMd * 2

            ColumnLayout {
                id: activityColumn
                anchors.fill: parent
                spacing: Theme.spacingSm

                Text { text: "Recent activity"; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeSubheading; font.bold: true }

                Repeater {
                    model: [
                        { text: "Downloaded VOD from northernlion", platform: "twitch" },
                        { text: "Clip saved from xqc", platform: "kick" },
                        { text: "Scheduled download created for hasanabi", platform: "twitch" }
                    ]
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm
                        PlatformBadge { platform: modelData.platform }
                        Text { text: modelData.text; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeBody; Layout.fillWidth: true; elide: Text.ElideRight }
                    }
                }
            }
        }
    }
}
