import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

// FASE 21b: rows come from `historyModel` (qml_bridge/history_model.py).
Item {
    id: root

    Component.onCompleted: historyModel.refresh()

    EmptyState {
        anchors.fill: parent
        visible: historyModel.loaded && historyModel.count === 0
        title: "No download history"
        description: "Completed, failed and cancelled downloads are listed here."
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        visible: historyModel.count > 0
        contentWidth: availableWidth

        ColumnLayout {
            width: scroll.availableWidth
            spacing: Theme.spacingSm

            Repeater {
                model: historyModel
                delegate: SectionCard {
                    Layout.fillWidth: true
                    Layout.margins: Theme.spacingLg
                    Layout.bottomMargin: 0
                    Layout.preferredHeight: 56
                    RowLayout {
                        anchors.fill: parent
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
                            text: model.outcome !== "" ? model.outcome : model.size
                            color: model.outcome === "Failed" ? Theme.danger : Theme.textSecondary
                            font.pixelSize: Theme.fontSizeCaption
                        }
                        Text { text: model.date; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeCaption }
                        AppButton {
                            text: "Open folder"
                            onClicked: {
                                if (!historyModel.openFolder(model.id))
                                    ToastController.error("Folder not found");
                            }
                        }
                    }
                }
            }

            Item { Layout.preferredHeight: Theme.spacingLg }
        }
    }
}
