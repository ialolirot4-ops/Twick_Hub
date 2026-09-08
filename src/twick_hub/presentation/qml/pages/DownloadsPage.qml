import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

ScrollView {
    id: root
    contentWidth: availableWidth

    property var mockDownloads: [
        { name: "northernlion — VOD part 12", platform: "twitch", progress: 0.62 },
        { name: "xqc — full stream", platform: "kick", progress: 0.18 },
        { name: "hasanabi — clip compilation", platform: "twitch", progress: 0.91 }
    ]

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingSm

        Repeater {
            model: root.mockDownloads
            delegate: SectionCard {
                Layout.fillWidth: true
                Layout.margins: Theme.spacingLg
                Layout.bottomMargin: 0
                Layout.preferredHeight: 76

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.spacingXs

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm
                        PlatformBadge { platform: modelData.platform }
                        Text {
                            text: modelData.name
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontSizeBody
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: Math.round(modelData.progress * 100) + "%"
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSizeCaption
                        }
                        AppButton {
                            text: "Cancel"
                            onClicked: {
                                cancelDialog.targetName = modelData.name;
                                cancelDialog.open();
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 6
                        radius: 3
                        color: Theme.border
                        Rectangle {
                            width: parent.width * modelData.progress
                            height: parent.height
                            radius: 3
                            color: Theme.accent
                        }
                    }
                }
            }
        }

        Item { Layout.preferredHeight: Theme.spacingLg }
    }

    AppDialog {
        id: cancelDialog
        property string targetName: ""
        title: "Cancel this download?"
        message: "\"" + targetName + "\" will stop downloading. Progress made so far is discarded — this can't be undone."
        confirmLabel: "Cancel download"
        cancelLabel: "Keep downloading"
        destructive: true
        onAccepted: ToastController.info("Cancelled \"" + targetName + "\"")
    }
}
