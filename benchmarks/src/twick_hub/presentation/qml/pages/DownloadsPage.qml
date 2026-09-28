import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

// FASE 21b: rows come from `downloadsModel` (qml_bridge/downloads_model.py).
// Live progress is not persisted while a download runs, so the page asks
// for a refresh once a second — only while it is on screen AND something
// is still in flight. No timer ticks at idle or on other pages.
Item {
    id: root

    Component.onCompleted: downloadsModel.refresh()

    Timer {
        interval: 1000
        repeat: true
        running: root.visible && downloadsModel.hasActive
        onTriggered: downloadsModel.refresh()
    }

    EmptyState {
        anchors.fill: parent
        visible: downloadsModel.loaded && downloadsModel.count === 0
        title: "No active downloads"
        description: "Downloads you start appear here while they run. Finished ones move to History."
        actionLabel: "Find something to download"
        onActionRequested: NavigationController.navigate("search")
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        visible: downloadsModel.count > 0
        contentWidth: availableWidth

        ColumnLayout {
            width: scroll.availableWidth
            spacing: Theme.spacingSm

            Repeater {
                model: downloadsModel
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
                            PlatformBadge { platform: model.platform }
                            Text {
                                text: model.title
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontSizeBody
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            Text {
                                text: model.progressKnown
                                    ? model.statusLabel + " · " + Math.round(model.progress * 100) + "%"
                                    : model.statusLabel
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontSizeCaption
                            }
                            AppButton {
                                text: "Cancel"
                                onClicked: {
                                    cancelDialog.targetId = model.id;
                                    cancelDialog.targetName = model.title;
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
                                visible: model.progressKnown
                                width: parent.width * model.progress
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
    }

    AppDialog {
        id: cancelDialog
        property string targetId: ""
        property string targetName: ""
        title: "Cancel this download?"
        message: "\"" + targetName + "\" will stop downloading. Progress made so far is discarded — this can't be undone."
        confirmLabel: "Cancel download"
        cancelLabel: "Keep downloading"
        destructive: true
        onAccepted: {
            downloadsModel.cancel(targetId);
            ToastController.info("Cancelled \"" + targetName + "\"");
        }
    }
}
