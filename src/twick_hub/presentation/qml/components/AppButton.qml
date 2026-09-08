import QtQuick
import QtQuick.Controls.Basic
import TwickHub 1.0

// Base Controls (QtQuick.Controls.Basic) so the whole app's look comes
// from Theme, not a native/Fusion/Material style guessing the platform.
Button {
    id: root
    property bool primary: false

    implicitHeight: 36
    leftPadding: Theme.spacingMd
    rightPadding: Theme.spacingMd

    background: Rectangle {
        radius: Theme.radiusSm
        color: {
            if (root.primary) return root.down ? Qt.darker(Theme.accent, 1.15) : Theme.accent;
            return root.down ? Theme.border : (root.hovered ? Theme.surfaceElevated : "transparent");
        }
        border.width: root.primary ? 0 : 1
        border.color: Theme.border
        opacity: root.enabled ? 1.0 : 0.5
    }

    contentItem: Text {
        text: root.text
        color: root.primary ? Theme.accentText : Theme.textPrimary
        font.pixelSize: Theme.fontSizeBody
        font.bold: root.primary
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
