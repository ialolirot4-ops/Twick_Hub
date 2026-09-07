import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwitchLinkNext 1.0
import "../components"

ColumnLayout {
    id: root
    anchors.fill: parent
    anchors.margins: Theme.spacingLg
    spacing: Theme.spacingMd

    property var mockAccounts: [
        { platform: "twitch", connected: true, username: "your_twitch_login" },
        { platform: "kick", connected: false, username: "" }
    ]

    Repeater {
        model: root.mockAccounts
        delegate: SectionCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            RowLayout {
                anchors.fill: parent
                spacing: Theme.spacingMd

                PlatformBadge { platform: modelData.platform }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        text: modelData.connected ? modelData.username : "Not connected"
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSizeBody
                        font.bold: true
                    }
                    Text {
                        text: modelData.connected
                            ? "Signed in via browser session — used for GQL, playback, and Integrity."
                            : "Connect to search and download from " + (modelData.platform === "kick" ? "Kick" : "Twitch") + "."
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSizeCaption
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }

                AppButton {
                    text: modelData.connected ? "Disconnect" : "Connect"
                    primary: !modelData.connected
                    onClicked: ToastController.info((modelData.connected ? "Disconnecting" : "Connecting") + " isn't wired up yet — that's FASE 4a/5.")
                }
            }
        }
    }

    Item { Layout.fillHeight: true }
}
