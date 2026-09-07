import QtQuick
import TwitchLinkNext 1.0

Rectangle {
    id: root
    property string pageId: ""
    property string label: ""
    readonly property bool selected: NavigationController.currentPageId === pageId

    width: parent ? parent.width : 200
    height: 40
    radius: Theme.radiusSm
    color: {
        if (root.selected) return Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.16);
        return mouseArea.containsMouse ? Theme.surfaceElevated : "transparent";
    }

    Rectangle {
        visible: root.selected
        width: 3
        height: parent.height * 0.6
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        radius: 2
        color: Theme.accent
    }

    Text {
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.leftMargin: Theme.spacingMd
        text: root.label
        color: root.selected ? Theme.textPrimary : Theme.textSecondary
        font.pixelSize: Theme.fontSizeBody
        font.bold: root.selected
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: NavigationController.navigate(root.pageId)
    }
}
