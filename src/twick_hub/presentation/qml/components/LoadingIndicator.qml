import QtQuick
import TwickHub 1.0

// A single rotating arc rather than a multi-dot/particle spinner — one
// RotationAnimator is cheap to keep running; several independently
// animated children are not (Master Plan §36 priority: "bajo consumo").
Item {
    id: root
    property string label: "Loading…"
    implicitWidth: column.implicitWidth
    implicitHeight: column.implicitHeight

    Column {
        id: column
        spacing: Theme.spacingSm
        anchors.centerIn: parent

        Rectangle {
            id: arc
            width: 28
            height: 28
            radius: width / 2
            anchors.horizontalCenter: parent.horizontalCenter
            color: "transparent"
            border.width: 3
            border.color: Theme.border

            Rectangle {
                width: 8
                height: 8
                radius: 4
                color: Theme.accent
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.topMargin: -2
            }

            RotationAnimator on rotation {
                from: 0
                to: 360
                duration: 900
                loops: Animation.Infinite
                running: root.visible
            }
        }

        Text {
            text: root.label
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeCaption
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }
}
