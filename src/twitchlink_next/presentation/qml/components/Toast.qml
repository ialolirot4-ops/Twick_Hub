import QtQuick
import TwitchLinkNext 1.0

Rectangle {
    id: root
    property string message: ""
    property string kind: "info" // "info" | "success" | "error"

    readonly property color accentColor: kind === "error" ? Theme.danger : (kind === "success" ? Theme.success : Theme.accent)

    width: Math.min(360, label.implicitWidth + Theme.spacingLg * 2)
    height: label.implicitHeight + Theme.spacingMd * 2
    radius: Theme.radiusMd
    color: Theme.surfaceElevated
    border.width: 1
    border.color: Theme.border

    Rectangle {
        width: 4
        height: parent.height
        radius: 2
        color: root.accentColor
    }

    Text {
        id: label
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingLg
        anchors.rightMargin: Theme.spacingMd
        anchors.topMargin: Theme.spacingMd
        anchors.bottomMargin: Theme.spacingMd
        text: root.message
        color: Theme.textPrimary
        font.pixelSize: Theme.fontSizeBody
        wrapMode: Text.WordWrap
        verticalAlignment: Text.AlignVCenter
    }
}
