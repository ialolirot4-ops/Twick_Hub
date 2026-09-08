import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

Item {
    id: root
    property bool simulateError: false
    property var mockLive: [
        { name: "northernlion", platform: "twitch", viewers: "4.2K", game: "Slay the Spire" },
        { name: "xqc", platform: "kick", viewers: "18.9K", game: "Just Chatting" }
    ]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingMd

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: root.mockLive.length + " favorites live right now"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeBody
                Layout.fillWidth: true
            }
            // Demo affordance for this phase only — proves ErrorState works;
            // real triggers (EventSub/polling failures) arrive in FASE 4d/10.
            AppButton {
                text: root.simulateError ? "Show results" : "Simulate refresh failure"
                onClicked: root.simulateError = !root.simulateError
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.simulateError
            spacing: Theme.spacingSm

            Repeater {
                model: root.mockLive
                delegate: SectionCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 64
                    RowLayout {
                        anchors.fill: parent
                        spacing: Theme.spacingSm
                        PlatformBadge { platform: modelData.platform }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text { text: modelData.name; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeBody; font.bold: true }
                            Text { text: modelData.game + " · " + modelData.viewers + " viewers"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeCaption }
                        }
                        AppButton { text: "Watch"; }
                        AppButton { text: "Download"; primary: true }
                    }
                }
            }
        }

        ErrorState {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.simulateError
            title: "Couldn't refresh live status"
            description: "The live monitor didn't respond in time. Your favorites list is unaffected — this only blocks the live/offline badges from updating."
            onActionRequested: root.simulateError = false
        }
    }
}
