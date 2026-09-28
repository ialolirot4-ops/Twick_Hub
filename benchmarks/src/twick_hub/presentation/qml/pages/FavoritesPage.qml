import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import TwickHub 1.0
import "../components"

// FASE 21b: rows come from `favoritesModel` (qml_bridge/favorites_model.py,
// attached to the engine's root context by qml_bridge/context.py).
Item {
    id: root

    Component.onCompleted: favoritesModel.refresh()

    EmptyState {
        anchors.fill: parent
        visible: favoritesModel.loaded && favoritesModel.count === 0
        title: "No favorites yet"
        description: "Channels you add as favorites show up here, with their live status."
        actionLabel: "Find a channel"
        onActionRequested: NavigationController.navigate("search")
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        visible: favoritesModel.count > 0
        contentWidth: availableWidth

        GridLayout {
            width: scroll.availableWidth
            columns: Math.max(1, Math.floor(width / 220))
            columnSpacing: Theme.spacingMd
            rowSpacing: Theme.spacingMd
            Layout.margins: Theme.spacingLg

            Repeater {
                model: favoritesModel
                delegate: SectionCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 92

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.spacingXs

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: model.channelName
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontSizeBody
                                font.bold: true
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            Rectangle {
                                visible: model.liveState === "live"
                                width: 8; height: 8; radius: 4
                                color: Theme.success
                            }
                        }

                        PlatformBadge { platform: model.platform }

                        Text {
                            text: model.liveState === "live" ? "Live now"
                                : model.liveState === "offline" ? "Offline" : "Status unknown"
                            color: model.liveState === "live" ? Theme.success : Theme.textSecondary
                            font.pixelSize: Theme.fontSizeCaption
                        }
                    }
                }
            }
        }
    }
}
