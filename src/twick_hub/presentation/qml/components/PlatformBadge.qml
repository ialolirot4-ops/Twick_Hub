import QtQuick
import TwickHub 1.0

// Small platform identity pill. This is the ONLY place Twitch purple or
// Kick green appear — see qml_bridge/theme.py's module docstring.
Rectangle {
    id: root
    property string platform: "twitch" // "twitch" | "kick"

    readonly property color platformColor: platform === "kick" ? Theme.kickBadge : Theme.twitchBadge
    readonly property string platformLabel: platform === "kick" ? "Kick" : "Twitch"

    width: label.implicitWidth + Theme.spacingSm * 2
    height: label.implicitHeight + Theme.spacingXs * 2
    radius: height / 2
    color: Qt.rgba(platformColor.r, platformColor.g, platformColor.b, 0.16)
    border.color: platformColor
    border.width: 1

    Text {
        id: label
        anchors.centerIn: parent
        text: root.platformLabel
        color: root.platformColor
        font.pixelSize: Theme.fontSizeCaption
        font.bold: true
    }
}
